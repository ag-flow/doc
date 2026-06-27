# MCHG — Catch-up feed (rattrapage des changements)

**Objectif.** Un endpoint **REST pur** (pas de MCP) qui renvoie, par curseur, les changements de documents depuis un point donné. C'est le filet du webhook best-effort : un externe qui a manqué des notifications (lui ou docflow down) se **resynchronise** en lisant ce feed — **suppressions comprises**.

**Dépend de.** `21_RW` (point d'alimentation du journal), `29_MWH` (même source que l'émission webhook), `28_MUI4` (route scopée workspace). Migration **`0008`**.

## Pourquoi un journal dédié (et pas un compteur sur le document)

Le curseur doit être **stable, total, monotone**. Un `updated_at` n'est ni unique ni à l'abri de l'horloge ; un compteur par document n'est pas un ordre global. → une **séquence Postgres** sur une table dédiée (`document_change_log.seq`) : strictement croissante, unique, infaillible comme curseur.

**Le point décisif — les suppressions.** `document_change_log.document_ref` n'est **pas** une FK en cascade : la ligne `D` doit **survivre** à la disparition du document. C'est précisément ce qu'une colonne `change_seq` posée *sur* `document` ne pourrait pas faire (elle partirait avec lui). Le journal dédié est la seule forme qui capte les deletes pour le rattrapage.

## Alimentation (couplée à `21_RW`, in-transaction)

Une ligne est insérée **dans la transaction** du write — jamais après — pour qu'aucun changement n'échappe au journal :

| Déclencheur | nature |
| --- | --- |
| création de document | `C` |
| nouvelle version de contenu (`document_version`) | `U` |
| nouvelle version de valeur (`properties_value_version`) | `P` |
| suppression de document | `D` |

Énumération **fermée** : `C | U | P | D`. Pas de trace de lecture (un feed de changements ne journalise que les mutations).

Le webhook (`29`) et ce feed partagent ce journal comme **source unique** : le push best-effort notifie en direct, le feed permet le pull de rattrapage.

## Endpoint (REST uniquement)

```
GET /ws/{wsSlug}/changes?since={cursor}&limit={n}
→ {
    "changes": [
      { "seq": 1042, "nature": "U", "document_id": "…", "occurred_at": "…" },
      …
    ],
    "next_cursor": 1058,
    "has_more": true
  }
```

- `since` : dernier `seq` vu par le client (0/absent = depuis le début). On renvoie `WHERE seq > since ORDER BY seq LIMIT n`.
- `next_cursor` : le plus grand `seq` du lot → le client le repasse en `since` au tour suivant.
- `has_more` : `true` si le lot était plein (le client peut reboucler immédiatement pour rattraper un gros retard).
- **Garantie** : avec ce protocole, le client **ne rate rien et ne revoit rien**.
- **Non exposé en MCP** : le rattrapage est un pattern d'intégration HTTP (polling), pas une action d'agent.

## Tâches (TDD)

- [ ] Migration `0008` + `apply`.
- [ ] Insertion in-transaction dans les chemins write/delete de `21_RW` (C/U/P/D).
- [ ] Endpoint `GET .../changes` : curseur `seq`, `limit`, `next_cursor`, `has_more`, scope workspace.
- [ ] Tests : ordre total, pas de doublon/saut entre deux pages, le `D` apparaît **après** suppression du document (document absent mais ligne présente).

## Definition of Done

1. ruff + mypy + tests verts.
2. Créer/modifier/supprimer quelques documents → `GET .../changes?since=0` renvoie les natures dans l'ordre `seq`, **dont le `D`** d'un document supprimé.
3. Paginer avec `limit=2` : enchaîner les `next_cursor` couvre tout, sans doublon ni trou.
4. Un document supprimé : son `D` reste lisible (le journal a survécu).
5. Endpoint **absent** de la surface MCP.

## Notes / décisions ouvertes

- **Rétention** du journal : croît indéfiniment ; une purge (par âge ou seq) sera à prévoir plus tard (additif).
- **Filtrage** (par bloc/type/nature) : aujourd'hui feed brut par workspace ; affinable plus tard.
- **Context7** avant code (asyncpg, identity columns).

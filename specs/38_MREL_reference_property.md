# MREL — Type de propriété `reference` (relation typée)

> **Disclaimer.** Cette spec a été écrite à partir des specs précédentes présentes dans le répertoire `specs/`. Une fois le travail à faire bien compris, **réévalue les impacts** et **assure-toi que les hypothèses décrites dans ce fichier sont toujours valides** (schéma réel des migrations, noms de tables/colonnes, contraintes, API des libs). Utilise tout outil/plugin qui aide à brainstormer et à vérifier pour cela : **Context7** (API des libs), **Serena** (navigation sémantique du code existant), skill **`brainstorming`** avant d'écrire, **`verification-before-completion`** avant de clore. Quand tu poses une question sur une **décision ouverte**, accompagne-la toujours d'un **minimum de contexte** — l'enjeu, les options envisagées et leurs conséquences — pour que l'utilisateur puisse trancher sans avoir à relire toute la spec.

**Objectif.** Ajouter un type de propriété **`reference`** : une propriété dont la **valeur est un autre document**, découvert par **recherche** (réutilise le picker de `31_MREF`). Contrairement aux liens markdown de `31` (souples, enfouis dans le contenu, « détecter pas empêcher »), une `reference` est une **relation structurée** : portée par une propriété, **validée** à l'écriture, **filtrable** dans les vues (`37_MVIEW`), **visible** en backlink (`33_MBLK`). C'est la relation typée que Notion a et qu'Obsidian Bases n'a pas.

**Dépend de.** `34_MPTS` (extension du type de propriété), `31_MREF` (picker de recherche, philosophie FK molle), `33_MBLK` (panneau backlinks), `37_MVIEW` (filtres). Migration **`0024`**.

---

## ⚠ Choix structurant à confirmer avant code

**Cible typée ou libre.**
- **Reco (typée)** : la `properties_def` de type `reference` déclare un **type de document cible autorisé** (`target_functional_type_ref`, ex. `assignee → person`). Le picker ne propose que des documents de ce type, et l'écriture **valide** que la cible est bien de ce type. C'est ce qui en fait une *vraie* relation (l'équivalent du « relation to database X » de Notion), et ça rend les vues bien plus utiles.
- Alternative (libre) : `target_functional_type_ref` nullable = `null` ⇒ pointe **n'importe quel** document. Plus souple, moins de garde-fou.
- *Conséquence* : on garde **les deux** dans le modèle — colonne **nullable**. `null` = cible libre, renseignée = cible typée. **Reco : autoriser la déclaration typée**, sans l'imposer. Coût : une colonne + une validation. Confirme qu'on expose bien le réglage de type cible dès la V1.

---

## Principe : relation structurée, cible molle

Deux régimes cohabitent dans docflow et **ne se confondent pas** :

| | `31_MREF` — lien de contenu | `38_MREL` — relation typée (cette spec) |
|---|---|---|
| Où | dans le markdown du corps | valeur d'une **propriété** |
| Découverte | `/link` dans l'éditeur | picker de la propriété |
| Validation | aucune (détecter pas empêcher) | **type de cible vérifié à l'écriture** |
| Requêtable | non (juste tracé) | **oui** (filtre de vue, backlink) |
| Cible disparue | orpheline, détectée | orpheline, détectée |

Point commun : **FK molle**. La cible peut disparaître sans blocage ni cascade ; un anti-join révèle les relations orphelines (comme `31`). On **valide à l'affectation** (type + existence), on **n'empêche pas** la disparition ultérieure.

## Modèle (`0024`)

**Sur `properties_defs`** :
- `type` : étendre le `CHECK` pour ajouter `'reference'`.
- `target_functional_type_ref` uuid **NULL** FK → `functional_type` (RESTRICT) : type de document cible autorisé ; `null` = cible libre (décision ci-dessus).

**Sur `properties_values`** :
- `target_document_ref` uuid **NULL** — **sans FK** (molle, comme `document_reference.target_ref` de `31`). Renseigné pour une valeur de type `reference`, null sinon.
- Remplacer le `CHECK` actuel (`NOT (value IS NOT NULL AND allowed_value_ref IS NOT NULL)`) par un **exactly-≤1** :
  ```sql
  CHECK (num_nonnulls(value, allowed_value_ref, target_document_ref) <= 1)
  ```
- `CREATE INDEX ON properties_values(target_document_ref)` (filtres de vue + anti-join orphelins).

**Invariants applicatifs** (testés) :
- type `reference` → `target_document_ref` renseigné, `value` et `allowed_value_ref` null.
- à l'écriture : la cible **existe** (au moment de l'affectation) **et** son `functional_type` correspond à `target_functional_type_ref` si déclaré → sinon **rejet**.
- la cible appartient au **même workspace** (cloisonnement).

## Picker (réutilise `31_MREF`)

L'endpoint de recherche de `31` est réutilisé, avec un filtre de type optionnel :

```
GET /ws/{wsSlug}/documents/search?q={texte}&type={ftypeSlug}
→ [ { "id", "title", "type", "bloc" }, … ]
```

Le panneau de propriétés (`25_MUI2`) affiche, pour une propriété `reference`, un champ qui ouvre ce picker (filtré sur `target_functional_type_ref` si déclaré). On stocke l'**id**, on affiche le **titre courant** (jamais l'id à l'écran).

## Intégrations

- **Backlinks (`33`)** : le panneau « Référencé par » d'un document gagne une section **« Relations entrantes »** — les documents qui le pointent **via une propriété `reference`**, étiquetés par le **label de la propriété** (ex. « Export PDF — *assignee* »). Source = `properties_values.target_document_ref` indexé.
- **Vues (`37`)** : `reference` devient un **field de filtre** — opérateurs `is` (cible = doc X), `is_empty` / `not_empty`. L'`EXISTS` du builder s'étend sur `target_document_ref`. Group-by par référence = additif (colonnes = documents cibles) — hors V1.
- **Orphelins** : anti-join `properties_values.target_document_ref` ⟂ `document` → relations cassées, mêmes badges que `31`.

## Tâches (TDD)

- [ ] Migration `0024` (type `reference`, `target_functional_type_ref`, `target_document_ref`, CHECK `num_nonnulls`, index) + `apply` idempotent.
- [ ] Validation d'affectation : cible existante + bon type + même workspace ; rejet documenté sinon (3 tests de rejet).
- [ ] Picker filtré par type (extension du `search` de `31`).
- [ ] Panneau propriétés : champ `reference` (recherche → id stocké, titre affiché, live).
- [ ] Section « Relations entrantes » dans le panneau backlinks (`33`).
- [ ] Filtre de vue `reference` (`is` / `is_empty` / `not_empty`) dans le builder de `37`.
- [ ] Anti-join orphelins + badge.
- [ ] Context7 avant code (asyncpg `num_nonnulls`, picker BlockNote/shadcn).

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts ; `npm run build`.
2. Migration `0024` rejouable base vierge **et** existante ; CHECK `num_nonnulls(...) <= 1` vérifié (test des combinaisons interdites) ; `apply` idempotent.
3. Aucune requête non paramétrée ; Context7 consulté.

### Critères fonctionnels
4. Déclarer une propriété `reference` avec un type cible → le picker ne propose **que** des documents de ce type.
5. Affecter une cible du **mauvais type**, d'un **autre workspace**, ou **inexistante** → **rejet** avec message.
6. La valeur affiche le **titre courant** de la cible ; renommer la cible met à jour l'affichage sans action.
7. La cible apparaît en **« Relations entrantes »** sur le document pointé, étiquetée par le label de la propriété.
8. Une vue filtrée `assignee is Alice` ne renvoie que les documents pointant Alice.
9. Supprimer la cible → la relation devient **orpheline** (badge), **sans blocage**.

### Scénario de manipulation (recette de démonstration)
Dérouler ces étapes prouve la valeur de bout en bout :

1. Dans `projet-x`, créer un type **Personne** et deux documents `Alice`, `Bob` de ce type. Sur le type **Feature**, ajouter une propriété **`assignee`** de type **`reference`**, cible = **Personne**.
2. Ouvrir la feature **« Export PDF »**, champ `assignee` → le picker ne propose qu'`Alice` / `Bob` (pas les features). Choisir **Alice**. Enregistrer.
3. Tenter d'affecter une **Feature** comme `assignee` → impossible (picker filtré) ; via l'API, forcer une cible d'un autre type → **rejet**.
4. Ouvrir le document **`Alice`** → section **« Relations entrantes »** : « Export PDF — *assignee* », cliquable.
5. Dans la vue board **« À développer »** (`37`), ajouter le filtre **`assignee is Alice`** → seules les features d'Alice restent.
6. Renommer `Alice` en `Alice Martin` → l'affichage de `assignee` et la relation entrante suivent. Supprimer `Alice Martin` → la relation passe **orpheline** (badge), la feature n'est pas bloquée.

**Ce que ça apporte.** Les relations (`assignee`, `dépend de`, `composant`, `owner`…) deviennent des **données de première classe** : validées à la saisie, filtrables dans les vues, traçables en backlink. C'est le saut que ni Obsidian Bases (pas de relations) ni Logseq (pas d'interface agent) ne couvrent proprement — et ça reste exposable au MCP.

## Notes / décisions ouvertes

- **Cible `data_block`** : V1 = cible **document** uniquement. Pointer un bloc structuré (epic/feature) viendra si besoin.
- **Cardinalité** : V1 = **mono-valeur** (une cible). Le **multi-valeur** (ex. `reviewers` = plusieurs personnes) est traité en **`39_MMV`** et s'appliquera aussi bien aux `reference` qu'aux `restricted_list`.
- **Group-by par référence** dans les vues (colonnes = documents cibles) : additif post-V1.
- **Rollups** (agréger une propriété de la cible, ex. somme des charges des sous-features) : hors périmètre, à évaluer plus tard — c'est le cran au-dessus de Notion.

# MREF — Référencement & cohérence des liens

**Objectif.** Permettre à un document d'en **référencer** un autre, via une découverte par **recherche** (jamais d'id saisi à la main), tracer ces liens dans une table à **FK molle**, et **détecter les liens cassés** pour les corriger. Philosophie : **détecter, pas empêcher** — les liens cassent librement, l'outil les retrouve.

**Dépend de.** `21_RW` (parsing au save), `24_MUI1` (éditeur BlockNote), `28_MUI4` (écran des blocs scopé workspace). Migrations **`0009`** (références) et **`0010`** (recherche titres).

## Principe : détecter, pas empêcher

Aucune intégrité dure. La cible d'un lien peut disparaître sans blocage ni cascade : la référence devient **orpheline**, et c'est une **requête** (anti-join) qui révèle les incohérences. C'est la bonne posture pour une base vivante (interdire une suppression à cause d'un lien entrant est insupportable à l'usage).

## Découverte du lien (UX éditeur)

- Entrée par **`/link`** : un item du menu slash de BlockNote qui **ouvre un menu de recherche** de documents. *(alternative : un caractère déclencheur dédié style mention — à confirmer ; `/link` retenu par défaut, garde `@` libre pour de futures mentions d'utilisateurs.)*
- Le menu utilise le **`getItems` asynchrone** de BlockNote : à chaque frappe, il interroge un endpoint de recherche et affiche `{title, type, bloc}`.
- L'utilisateur tape des **mots du titre**, choisit un document → l'éditeur insère un lien **portant l'id** mais affichant le **titre** : `[Titre](docflow://doc/{id})`. **L'id n'est jamais saisi ni affiché.**
- **Couture RAG** : `getItems` est le seul point à changer demain. Aujourd'hui → base docflow (trigram titres). Demain → **appel HTTP au service agflow-rag** (frontière de base, pas de jointure SQL cross-base). Même contrat UI, le menu ne bouge pas.
- **V1** : lien markdown simple (parsé au save). **V2** (optionnel) : contenu inline custom BlockNote qui se **colore en rouge** si la cible est orpheline, directement dans l'éditeur.

## Recherche de documents (endpoint)

```
GET /ws/{wsSlug}/documents/search?q={texte}&limit={n}
→ [ { "id": "…", "title": "…", "type": "feature", "bloc": "…" }, … ]
```

- Titre via **`pg_trgm`** : `title ILIKE '%' || :q || '%'`, scopé workspace, limité à `n`.
- C'est ce que `getItems` appelle. Le **contenu n'est pas cherché** (réservé au RAG).

## Modèle — `document_reference` (FK molle, `0009`)

`id`, `source_ref` (FK `document` **CASCADE**), `target_ref` (uuid **NU, sans FK** → molle), `target_label` (texte du lien au save), `workspace_technical_key` (du source, dénormalisé), `created_at`, `UNIQUE(source_ref, target_ref)`, index sur `target_ref`.

Asymétrie clé : **source en CASCADE** (le citant fait autorité sur ses liens), **cible sans contrainte** (elle peut disparaître). `target_label` garde le texte du lien → un lien cassé s'affiche *« lien vers “Spec authentification” »*, pas un id nu.

## Parsing au save (dans la transaction `21_RW`)

À chaque écriture de contenu, **dans la même transaction** que le bump de version et le `change_log` :

1. parser le markdown du document, extraire les `docflow://doc/{id}` (+ le texte du lien) ;
2. **remplacer** (pas accumuler) : supprimer les `document_reference WHERE source_ref = ce doc`, réinsérer les références courantes (`target_ref` = id extrait, `target_label` = texte). → la table est **dérivée du contenu**, reconstruite à chaque save ;
3. les ids non parsables / mal formés sont ignorés (pas d'échec du save).

## Détection d'orphelins (anti-join)

```sql
select r.source_ref, r.target_ref, r.target_label
from document_reference r
left join document d on d.doc_technical_key = r.target_ref
where d.doc_technical_key is null;          -- cible disparue = orphelin
```

L'index sur `target_ref` garde l'anti-join rapide à grande échelle.

## Visualisation (écran des blocs)

Par bloc : compter les documents ayant ≥ 1 référence orpheline → **badge d'alerte** (« 3 documents avec liens cassés »). Au clic, détail : document source + `target_label` (lisible même orphelin) → l'utilisateur sait quoi corriger. C'est l'outil de traçabilité de cohérence.

## Tâches (TDD)

- [ ] Migrations `0009` (références) + `0010` (pg_trgm + index) + `apply`.
- [ ] Endpoint recherche titres (trigram, scope workspace, limit).
- [ ] Parser de liens `docflow://doc/{id}` + extraction du label (testable isolé).
- [ ] Rafraîchissement des références au save (remplacement) **dans la transaction `21_RW`**.
- [ ] Requête de détection d'orphelins + agrégat par bloc.
- [ ] Éditeur : item `/link` → menu recherche (`getItems` async) → insertion du lien par id.
- [ ] Écran blocs : badge liens cassés + détail.
- [ ] Tests : insertion par recherche, parsing/remplacement au save, orphelin après suppression de cible, badge par bloc.

## Definition of Done

1. ruff + mypy + tests verts ; `npm run build` côté front.
2. `/link` + frappe → la recherche renvoie les docs par titre ; sélection insère `[Titre](docflow://doc/{id})`, id jamais affiché.
3. Save → `document_reference` reflète exactement les liens du contenu (un lien retiré disparaît de la table).
4. Supprimer une cible → la référence devient orpheline, **sans blocage** ; l'anti-join la liste.
5. Écran blocs → badge « liens cassés » avec le `target_label` lisible.
6. **Context7** avant code (BlockNote suggestion menus / `getItems` async ; pg_trgm).

## Notes / décisions ouvertes

- **Déclencheur** : `/link` retenu ; caractère dédié (`@`) en alternative — à confirmer.
- **Portée** : intra-workspace pour le V1 (la recherche ne renvoie que le workspace courant). Le **cross-workspace** (vers un workspace public) viendra avec la visibilité publique + propriété de workspace — non modélisées à ce jour.
- **RAG** : bascule future de `getItems` vers le service agflow-rag (appel HTTP, pas de jointure cross-base — le moteur héberge les trois bases mais elles sont isolées).
- **V2** : contenu inline custom pour surligner les liens cassés dans l'éditeur.

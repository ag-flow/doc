# MRW — Lecture/écriture documents & valeurs

**Objectif.** Le socle d'instance : lire et écrire le **contenu** d'un document et les **valeurs de propriété**, avec versioning (audit), validation applicative, et concurrence optimiste. C'est la brique dont dépend tout le front du lot 2 (éditeur, panneau de propriétés, arbre).

**Dépend de.** M1 (foundation/`apply`), `0001` + `0002` (poussés), et les migrations **additives** de ce lot : `0003_document_versioning`, `0004_property_value_versioning`, `0005_workspace_archive`. Aucun fichier existant n'est réécrit.

## Forme du modèle au terme des migrations

- `document` (head) : `doc_technical_key`, `title` (dénormalisé courant), `type`, `functional_type_ref?`, `parent?`, **`version`**, `workspace_technical_key`, `created_at`, `updated_at`. *(plus de `contenu`)*
- `document_version` : `version_technical_key`, `document_ref`, `version_number`, `title`, `content`, `created_at`, `UNIQUE(document_ref, version_number)`.
- `properties_values` (head, identité pure) : `id`, `document_ref`, `property_def_ref`, **`version`**, `workspace_technical_key`, `UNIQUE(document_ref, property_def_ref)`. *(plus de `value`/`allowed_value_ref`/timestamps)*
- `properties_value_version` : `version_technical_key`, `property_value_ref`, `version_number`, `value`, `allowed_value_ref`, `created_at`, `UNIQUE(property_value_ref, version_number)`, `CHECK(not(value and allowed_value_ref))`.

**Invariants** (tenus applicativement) :
- `document.version` == `version_number` de la version courante du document.
- `properties_values.version` == `version_number` de la version courante de la valeur.
- `document.title` == `title` de la version courante (dénormalisation à maintenir dans la même transaction).
- une valeur porte le même `workspace_technical_key` que son document.

## Lecture

- **Document courant** : `title`/`version` depuis le head ; `content` depuis `document_version WHERE document_ref = D AND version_number = document.version`.
- **Arbre** : liste à plat des `document` d'un workspace (titre dénormalisé → **sans jointure**), arborescence reconstruite via `parent`. Filtre préservant le chemin (les ancêtres d'un nœud retenu restent visibles) — logique côté lecture/front.
- **Valeurs courantes** : pour chaque `property_def` du `functional_type` du document, la valeur courante = `properties_value_version WHERE property_value_ref = PV AND version_number = PV.version`. Absence → on retombe sur `properties_defs.default_value`.
- **Historique** : `… ORDER BY version_number DESC` sur la table de version concernée (consultation ; pas de revert pour l'instant).

## Écriture — validation des valeurs de propriété

Avant tout bump, le service valide (sinon **422** avec le `message` de la contrainte, ou un message générique) :

1. **Cohérence type↔document** : la `property_def` doit appartenir au `functional_type_ref` du document. Un document sans `functional_type_ref` n'a aucune valeur.
2. **Exactly-one-of selon le type** : `text`/`int` → `value` rempli, `allowed_value_ref` nul ; `restricted_list` → `allowed_value_ref` pointant une `allowed_value` **de cette def**, `value` nul. (Le CHECK base interdit « les deux » ; l'appli impose « le bon selon le type ».)
3. **`required`** : une def `required` sans valeur effective est rejetée.
4. **Coercition & contraintes** : `int` validé numériquement + `min`/`max` ; `text` + `min_length`/`max_length`/`pattern` (regex évaluée par l'appli, pas Postgres). `restricted_list` : la valeur doit exister dans `properties_allowed_values` de la def.

## Écriture — bump versionné + concurrence optimiste

Toute écriture (contenu **ou** valeur) suit le **même patron**, dans **une transaction** :

```
SELECT version FROM <head> WHERE <clé> = $id FOR UPDATE;   -- verrou + lecture de n
IF n <> $expected_version
    -> 409 Conflict + état courant (version n + contenu/valeur actuels), ROLLBACK, rien écrit
INSERT INTO <version_table> (..., version_number = n + 1, <données>);
UPDATE <head> SET version = n + 1 [, title=$title, updated_at=now() pour document]
       WHERE <clé> = $id;
COMMIT;
```

- **`FOR UPDATE`** sérialise les écrivains sur la ligne → la comparaison de version est fiable.
- **`UNIQUE(..., version_number)`** est le filet (pas de doublon de numéro).
- **Lock optimiste** : `expected_version` obligatoire en entrée ; mismatch → **409 + état courant**. **Aucune écriture** sur conflit.
- **Réconciliation déléguée au code appelant** : le 409 fournit le matériau (version + valeur/contenu courants) ; le store ne fusionne pas. (Contenu → écran 3 volets ; valeur → encart 3 valeurs par champ, résolution **par champ**.)

Le bump des valeurs est **par propriété** (chaque `properties_values` a sa propre `version`) : un conflit ne tombe que sur la propriété réellement contestée.

## Surface (factorisée REST / MCP / CLI)

Une **seule couche service** (Python testable) ; REST, MCP et CLI ne sont que des adaptateurs.

| Opération | Entrée clé | Sortie |
| --- | --- | --- |
| lire document | `doc_id` | `{title, content, version, functional_type_ref, parent}` |
| écrire contenu | `doc_id, title, content, expected_version` | `200 {version}` \| `409 {version, title, content}` |
| lister arbre | `workspace` | `[{doc_id, title, type, parent, functional_type_ref}]` |
| lire valeurs | `doc_id` | `[{property_def, value|allowed_value, version}]` (défaut si absente) |
| écrire valeur | `doc_id, property_def, value|allowed_value, expected_version` | `200 {version}` \| `409 {version, value}` \| `422 {message}` |

## Tâches (TDD — la validation et le bump sont testables sans Postgres)

- [ ] Migrations `0003`/`0004`/`0005` (additives) + passage de `apply`.
- [ ] Service de **validation de valeur** : type↔doc, exactly-one-of, required, min/max/min_length/max_length/pattern, appartenance allowed_value. Messages.
- [ ] Service de **bump versionné** générique (head + table de version) factorisé document/valeur : `FOR UPDATE`, `expected_version`, insert n+1, update head, maintien des invariants (dont `title` dénormalisé + `updated_at` côté document).
- [ ] Mapping **409 + état courant** et **422 + message**.
- [ ] Lecture : document courant, valeurs courantes (défaut si absente), arbre à plat.
- [ ] Adaptateurs REST (+ CLI a minima) sur la couche service.

## Definition of Done

1. ruff + mypy + tests verts.
2. Sur un workspace **déjà peuplé par un import de template** (scénario réaliste) : créer un document de type `feature`, écrire son contenu (v1 → v2), vérifier `document.version` et la version courante alignées.
3. Écrire une valeur `statut` (restricted_list) → version 1 ; la rejouer avec un mauvais `expected_version` → **409 + état courant, base inchangée** (test d'état).
4. Valeur `budget_jours = -1` → **422** avec le message de la contrainte `min`.
5. `restricted_list` pointant une `allowed_value` d'une autre def → **422**.
6. Board : « features en statut `done` du workspace » via la jointure head→version (index `idx_pvalue_version_allowed`).
7. Pitfalls : requêtes paramétrées, transaction unique, slugs immuables, aucun secret.

## Notes / décisions ouvertes

- **Board en jointure assumée** (head→version) — choix acté ; redénormaliser la valeur courante sur le head seulement si un board lent est *mesuré*.
- **Pas de revert** pour l'instant : le `version_number` sert à l'audit et à voir le nombre de changements ; le revert s'ajoutera plus tard (réécrire une valeur en repartant d'une version d'historique).
- **Context7** avant le code (asyncpg transactions/`FOR UPDATE`, pydantic v2).
- Roadmap `00_README` non modifiée (pas de churn) : ce milestone dépend de M1 + `0003`/`0004`/`0005`, et précède les lots front (éditeur, panneau propriétés, arbre).

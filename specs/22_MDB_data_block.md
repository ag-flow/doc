# MDB — data_block (conteneur racine des documents)

**Objectif.** Gérer les **blocs** : conteneurs nommés et typés d'un workspace, chacun appliquant un **modèle** (un type racine importé). Le bloc est la racine sous laquelle vit un arbre de documents. C'est le point de départ du flux : *workspace → import du modèle → créer un bloc → Add → premier document*.

**Dépend de.** M3 (workspace), M4 (types importés), `0001`/`0002` poussés. Introduit la migration additive **`0006`** (chaînon manquant ci-dessous).

## Le chaînon manquant (à acter en premier)

Le `0001` crée bien `data_block` (`functional_type_ref` not null, `parent` self-FK, scope workspace), **mais `document` ne référence pas `data_block`**. Or ton flux « je suis dans le bloc, j'appuie sur Add → un document apparaît dans le bloc » exige ce lien. Sans lui, documents et blocs sont déconnectés.

→ Migration additive, base vierge (table vide, donc `NOT NULL` direct possible) :

```sql
-- 0006_document_block_link.sql  (additif)
alter table document
    add column data_block_ref uuid not null
        references data_block(id) on delete restrict;
create index idx_document_block on document(data_block_ref);
-- data_block_ref DÉNORMALISÉ sur chaque document (comme workspace_technical_key) :
-- "tous les documents du bloc B" = WHERE data_block_ref = B, à plat.
-- Invariant : data_block_ref d'un document == celui de son parent (héritage du bloc).
```

## Rôle et sémantique du bloc

- `data_block.functional_type_ref` = le **type racine** appliqué au bloc (le modèle). Les documents racines du bloc (`parent IS NULL`) sont de ce type.
- `parent` (self-FK, optionnel) = organisation hiérarchique des blocs eux-mêmes (dossiers de blocs). `ON DELETE restrict`.
- `slug` **immuable**, unique par workspace ; `label` renommable.

## Création d'un bloc

Entrée : `workspace`, `functional_type` (racine), `slug`, `label`, `parent?`.
Validations (sinon **422**) :
1. le `functional_type` appartient au **workspace** cible ;
2. c'est un **type racine** du modèle (`parent IS NULL`) — un bloc s'ancre sur une racine, pas sur un type intermédiaire ;
3. `slug` valide (`^[a-z0-9][a-z0-9_-]*$`) et libre dans le workspace ;
4. `parent?` est un bloc du même workspace.

## Suppression / archivage

- Suppression bloquée (`RESTRICT`) si le bloc contient des documents → on **archive** plutôt (cohérent avec l'archivage workspace `0005`). *(Si tu veux un `archived_at` sur le bloc aussi, c'est une migration additive `0007` — à décider.)*

## Tâches (TDD)

- [ ] Migration `0006` + passage `apply`.
- [ ] Service bloc : create/list/get, validations (type du workspace, type racine, slug libre/immuable, parent même workspace).
- [ ] Repository : liste des blocs d'un workspace (+ arbre de blocs via `parent`).
- [ ] Adaptateurs REST + CLI.

## Definition of Done

1. ruff + mypy + tests verts.
2. Sur un workspace importé `agile-basic`, créer un bloc lié au type racine `epic` → OK.
3. Créer un bloc lié à `feature` (type non-racine) → **422** (pas une racine).
4. Créer un bloc avec un type d'un **autre** workspace → **422**.
5. `slug` dupliqué dans le workspace → **422**.

## Notes / décisions ouvertes

- **Multi-racines.** Tu avais évoqué un choix de type **au niveau du Add dans le bloc** quand le modèle a deux types racines. Or `functional_type_ref` (unique, not null) lie le bloc à **une** racine. Deux lectures :
  - **(a)** un bloc = une racine ; un modèle à deux racines ⇒ deux blocs. **Propre, zéro migration — défaut retenu.**
  - **(b)** un bloc applique le modèle entier (plusieurs racines, choix au Add) ⇒ il faut délier le bloc du type (migration rendant `functional_type_ref` nullable + réf. au template). À demander si tu y tiens.
  Le choix de type au Add reste pleinement utile **en profondeur** (sous une `feature` : `story` ou `atdd`).
- `data_block_ref` dénormalisé : invariant « enfant hérite le bloc du parent » tenu à la création (spec MTC).

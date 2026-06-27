# M6 — Data blocks arborescents

## Objectif

CRUD `data_block` : entité structurée typée (ex. une Epic concrète) formant un arbre
par `parent`. Contrainte miroir (I-5) : le `functional_type_ref` de l'enfant doit être
un fils direct du `functional_type_ref` du parent ; un bloc racine doit avoir un type racine.

## Routes exposées

| Méthode | URL | Auth |
|---------|-----|------|
| GET | `/workspaces/{ws}/blocks` | admin |
| POST | `/workspaces/{ws}/blocks` | admin |
| GET | `/workspaces/{ws}/blocks/{block_slug}` | admin |
| PATCH | `/workspaces/{ws}/blocks/{block_slug}` | admin |
| DELETE | `/workspaces/{ws}/blocks/{block_slug}` | admin |

## Invariants applicatifs

- **I-1** : enfant = même workspace que le parent (vérifié à l'écriture).
- **I-5** (contrainte miroir) : le `functional_type_ref` de l'enfant doit être
  un fils direct du `functional_type_ref` du parent dans la hiérarchie des types.
  Un bloc racine (parent=null) doit avoir un type racine (parent=null dans functional_type).
- Slug unique par workspace.
- Delete RESTRICT si enfants → 409.

## Definition of Done

- ruff + mypy propres
- Tests : CRUD, slug unique, I-1, I-5 miroir, delete bloqué si enfants

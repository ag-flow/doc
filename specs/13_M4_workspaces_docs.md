# M4 — Workspaces et documents arborescents

## Objectif

CRUD complet pour `workspace` et `document` (arbre markdown). Les documents
peuvent être typés (`functional_type_ref`) et forment un arbre via `parent`.

## Routes exposées

### Workspaces

| Méthode | URL | Auth | Description |
|---------|-----|------|-------------|
| GET | `/workspaces` | admin | Lister tous les workspaces |
| POST | `/workspaces` | superadmin | Créer un workspace |
| GET | `/workspaces/{ws_slug}` | admin | Détail d'un workspace |
| PATCH | `/workspaces/{ws_slug}` | superadmin | Mettre à jour label / description |
| DELETE | `/workspaces/{ws_slug}` | superadmin | Supprimer (cascade → tout le contenu) |

### Documents

| Méthode | URL | Auth | Description |
|---------|-----|------|-------------|
| GET | `/workspaces/{ws_slug}/documents` | admin | Lister les documents |
| POST | `/workspaces/{ws_slug}/documents` | admin | Créer un document |
| GET | `/workspaces/{ws_slug}/documents/{doc_id}` | admin | Détail (UUID) |
| PATCH | `/workspaces/{ws_slug}/documents/{doc_id}` | admin | Mettre à jour |
| DELETE | `/workspaces/{ws_slug}/documents/{doc_id}` | admin | Supprimer (RESTRICT si enfants) |

`doc_id` = `doc_technical_key` (UUID).

## Invariants applicatifs

- **I-1** : parent d'un document doit appartenir au même workspace (vérifié à l'écriture).
- `functional_type_ref` d'un document doit appartenir au même workspace.
- Un document avec des enfants ne peut être supprimé (RESTRICT FK DB → 409).

## Definition of Done

- ruff + mypy propres
- Tests : CRUD workspace, unicité slug, isolation workspace parent document, delete bloqué si enfants
- Pas de secret en clair
- Migrations rejouables (pas de nouvelle migration — schéma déjà en place dans 0001_init.sql)

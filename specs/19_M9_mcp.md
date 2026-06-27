# M9 — Serveur MCP

## Objectif

Exposer le store docflow via le protocole MCP (Model Context Protocol).
Lecture/écriture sous le même RBAC. Namespace par workspace.

## Architecture

Le serveur MCP tourne sur `/mcp` (HTTP SSE ou stdio selon le mode de démarrage).
Il réutilise la pool asyncpg et les settings de l'application FastAPI.

## Outils MCP exposés

### Workspace scope

| Outil | Description | Auth |
|-------|-------------|------|
| `list_workspaces` | Lister les workspaces | admin |
| `list_types` | Lister les types fonctionnels d'un workspace | admin |
| `list_documents` | Lister les documents d'un workspace | admin |
| `get_document` | Lire un document (contenu markdown) | admin |
| `create_document` | Créer un document | admin |
| `update_document` | Modifier titre/contenu d'un document | admin |
| `list_property_values` | Lire les valeurs d'un document | admin |
| `set_property_value` | Écrire une valeur de propriété | admin |

## Auth

Le serveur MCP valide le JWT docflow passé en header `Authorization: Bearer` 
(même logique que l'API REST). Les outils respectent le RBAC admin/superadmin.

## Definition of Done

- ruff + mypy propres
- Tests unitaires : chaque outil MCP appelé directement (sans transport réseau)
- Le JWT est validé ; les appels sans token sont rejetés
- Pas de secret dans le payload MCP

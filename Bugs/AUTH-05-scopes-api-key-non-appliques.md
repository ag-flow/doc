# AUTH-05 — Scopes d'API key non appliqués sur documents/properties/types (fail-open)

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : auth / API keys
- **Fichiers** : `backend/src/docflow/documents/router.py` (aucun appel) ; `properties/router.py` ; `types/router.py` — contraste : `blocks/router.py`, `workspaces/router.py` appellent `check_api_key_scope`

## Description

L'application des scopes d'API key est **opt-in** par appel explicite à `check_api_key_scope`/`filter_*`. Les routers `documents`, `properties` et `types` ne l'appellent **jamais** (0 occurrence). Une clé API restreinte (read-only, un seul workspace/bloc) obtient donc un **accès CRUD complet** aux documents, valeurs de propriétés et types de **tous** les workspaces.

## Scénario de reproduction

1. Profil d'API key avec un seul scope `{workspace_slug:'A', block_slug:'X', read_only:true}`.
2. La clé appelle `POST /api/workspaces/B/documents` ou `PATCH .../documents/{id}`.
3. Aucun contrôle de scope → écriture acceptée dans le workspace B, hors périmètre.

## Impact

Les scopes d'API key sont sans effet sur le cœur du domaine : une clé lecture-seule limitée à un workspace peut tout écrire partout.

## Piste de correction

Appeler `check_api_key_scope(request, ws_slug, ...)` (avec `write=True` sur les mutations) dans chaque handler documents/properties/types, ou centraliser l'enforcement (dépendance de router) plutôt qu'un pattern fail-open par oubli possible.

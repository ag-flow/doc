# DOC-10 — Workspace archivé encore entièrement modifiable

- **Gravité** : 🟡 MINEUR (écart de spec)
- **Confiance** : haute (code) / moyenne (intention)
- **Zone** : domaine / workspaces
- **Fichiers** : `backend/src/docflow/workspaces/service.py:46-51` ; `db/helpers.py:21-28`

## Description

La spec `12_M3_workspace.md` dit « `list`/`get` filtrent `archived_at is null` par défaut » : seul `list` le fait. Surtout, `require_workspace` (utilisé par **tous** les modules de contenu) ignore `archived_at` : un workspace archivé reste intégralement modifiable (docs, types, vues, valeurs) — l'archivage n'est qu'un drapeau d'affichage de liste.

## Scénario de reproduction

1. Archiver un workspace.
2. `POST /workspaces/{ws}/documents` fonctionne toujours.

## Impact

L'archivage ne protège rien ; incohérence avec la spec.

## Piste de correction

Paramètre `allow_archived=False` sur `require_workspace`, refus 409/410 des écritures sur workspace archivé ; filtrer `get` par défaut.

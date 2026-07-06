# DOC-10 — Workspace archivé encore entièrement modifiable

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.
> `require_workspace(..., allow_archived=True)` par défaut (lectures inchangées).
> Les écritures du plan contenu passent `allow_archived=False` → 409 sur workspace
> archivé : documents (create/update/delete/exposed + valeurs de propriétés),
> blocs, types, propriétés (defs/valeurs autorisées/contraintes) et vues.
> Hypothèses documentées :
> - `get_workspace` continue de renvoyer un workspace archivé (pas d'endpoint de
>   désarchivage ; le masquer le rendrait ingérable). Le filtrage « get » de la spec
>   n'est donc pas appliqué ici, volontairement.
> - automations / webhooks / reactions ne sont pas couverts par cette passe (hors du
>   plan contenu « docs, types, vues, valeurs » nommé par la fiche).

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

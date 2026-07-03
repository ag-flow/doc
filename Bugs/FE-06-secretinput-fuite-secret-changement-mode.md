# FE-06 — SecretInput : secret exposé en clair lors d'un changement de mode

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : frontend / secrets
- **Fichiers** : `frontend/src/components/SecretInput.tsx:34-40, 60-67`

## Description

En mode « En local », la valeur tapée (masquée, `type=password`) est le secret brut. Si l'utilisateur change ensuite le select vers un wallet, `build(mode, raw)` réutilise `raw` comme **chemin** : la valeur devient `${vault://wallet:/<secret>}` et l'input passe en `type=text` → le secret **s'affiche en clair** et, si l'utilisateur enregistre, il part en base **dans la colonne de référence vault** (non traitée comme secret).

## Scénario de reproduction

1. OidcAdmin → taper le `client_secret` en mode local.
2. Changer d'avis et sélectionner un wallet.
3. Le secret s'affiche en clair ; « Enregistrer » le persiste dans `client_secret_ref`.

## Impact

Fuite d'un secret en clair à l'écran et en base (colonne de référence, non chiffrée comme un secret).

## Piste de correction

Vider `raw` lors d'un changement de mode LOCAL → wallet (et inversement).

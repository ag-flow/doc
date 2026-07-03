# FE-07 — `isSuperAdmin()` : `atob` échoue sur JWT base64url → UI admin masquée

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : frontend / auth
- **Fichiers** : `frontend/src/lib/api.ts:493-502`

## Description

Le payload JWT est encodé en **base64url** (`-` et `_`), que `atob` rejette (`InvalidCharacterError`). Le `catch` renvoie `false`. Selon le contenu binaire du payload (donc selon le token émis), un superadmin perd les entrées Templates/Utilisateurs/Vault/OIDC/Remote de la sidebar et l'onglet wallets de VaultAdmin.

## Scénario de reproduction

1. Se connecter en admin.
2. Si le token contient un `-`/`_` dans son payload encodé, la sidebar n'affiche plus la section admin.
3. Une reconnexion peut « réparer » — bug **intermittent**.

## Impact

Les sections d'administration disparaissent aléatoirement pour un superadmin légitime.

## Piste de correction

Convertir base64url → base64 (`.replace(/-/g,'+').replace(/_/g,'/')` + padding) avant `atob`.

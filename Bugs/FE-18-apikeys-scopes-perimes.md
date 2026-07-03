# FE-18 — ApiKeysPage : scopes affichés périmés après sauvegarde

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : frontend / API keys
- **Fichiers** : `frontend/src/pages/ApiKeysPage.tsx:184-208, 250`

## Description

`saveScopesMutation` invalide `['api-profiles']` mais **pas** `['api-profile', profile.id]`. Replier puis redéployer la carte (< 30 s) recharge les scopes depuis le cache **pré-sauvegarde** (`setScopes(fromScopeList(detail.scopes))`) — l'utilisateur croit la sauvegarde perdue et peut ré-enregistrer un état obsolète. Accessoirement, `setScopes` est appelé pendant le rendu (pattern derived-state fragile).

## Scénario de reproduction

1. Modifier et sauvegarder les scopes d'un profil.
2. Replier/redéployer la carte rapidement → anciens scopes réaffichés.

## Impact

Confusion utilisateur et risque de ré-enregistrer un état périmé.

## Piste de correction

Invalider aussi `['api-profile', profile.id]` dans `onSuccess`.

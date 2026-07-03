# FE-17 — Logout : cache TanStack Query non purgé

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : frontend / auth
- **Fichiers** : `frontend/src/components/Sidebar.tsx:81-84`

## Description

`logout()` fait `clearToken()` + navigate, **sans `queryClient.clear()`**. Après reconnexion avec un **autre compte** sur le même navigateur, les données du compte précédent (workspaces, documents, users admin) sont servies depuis le cache pendant la fenêtre de staleness.

## Scénario de reproduction

1. Se connecter en tant que A, naviguer.
2. Se déconnecter, se reconnecter en tant que B (< staleness).
3. Les données de A s'affichent brièvement.

## Impact

Fuite transitoire de données entre comptes sur un poste partagé.

## Piste de correction

`queryClient.clear()` au logout (et au 401 global — voir [FE-04](FE-04-login-401-recharge-page.md)).

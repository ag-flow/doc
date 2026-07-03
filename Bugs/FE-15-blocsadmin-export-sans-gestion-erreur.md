# FE-15 — BlocsAdmin `handleExport` : erreurs HTTP non gérées

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : frontend / export
- **Fichiers** : `frontend/src/pages/BlocsAdmin.tsx:222-238`

## Description

Le fetch d'export ne vérifie ni `r.ok` ni ne catch : un 401/500 télécharge un `<slug>.zip` contenant le **JSON d'erreur** ; un token expiré échoue silencieusement (pas de redirection puisque fetch brut). Le token est lu par littéral `localStorage.getItem('docflow_token')` au lieu de `getToken()`.

## Scénario de reproduction

Exporter un bloc avec un token expiré → un fichier `.zip` corrompu (contenant l'erreur) est téléchargé.

## Impact

Fichier d'export corrompu et absence de feedback d'erreur.

## Piste de correction

Passer par un helper `requestBlob` mutualisé avec la gestion 401, vérifier `r.ok`.

# DEP-06 — `/data/.env` de dev sans `ENCRYPTION_KEY` (divergence dev/prod)

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : déploiement / config
- **Fichiers** : `scripts/dev-deploy.sh:55-62` ; `scripts/.env.example` — vs `deploy/.env.example:18-26`, `prod-deploy.sh:60, 80`

## Description

`settings.encryption_key` est optionnelle (« absence = headers interdits ») ; prod la génère et l'exige, dev ne la génère pas. Sur test1, webhooks avec headers, wallets Harpocrate et secrets utilisateur sont donc **silencieusement inopérants** — précisément les features à valider sur l'environnement de test.

Au passage, `scripts/.env.example` dit « JWT_SECRET … 32 HEX CHARS » alors que le générateur produit 64 hex (`token_hex(32)`) ; `deploy/.env.example` dit correctement 64.

## Impact

Fonctionnalités liées au chiffrement invalidables sur l'environnement de test, sans signal.

## Piste de correction

Générer `ENCRYPTION_KEY` dans `dev-deploy.sh` comme en prod ; supprimer `scripts/.env.example` au profit de `deploy/.env.example` (source unique). Voir aussi [DEP-01](DEP-01-identifiants-admin-bootstrap-morts.md) et [DEP-02](DEP-02-scripts-sql-doublons-divergents.md).

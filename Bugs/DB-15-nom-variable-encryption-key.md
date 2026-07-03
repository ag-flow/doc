# DB-15 — Messages d'erreur citant `DOCFLOW_ENCRYPTION_KEY` au lieu de `ENCRYPTION_KEY`

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : db / secrets — cohérence config
- **Fichiers** : `backend/src/docflow/vault/router.py:26` ; `webhooks/service.py:85, 122` (+ commentaires migrations 0012/0017)

## Description

`Settings` n'a pas d'`env_prefix` ; le déploiement (`deploy/.env.example`, `prod-deploy.sh`) utilise bien `ENCRYPTION_KEY`. Mais plusieurs messages d'erreur mentionnent `DOCFLOW_ENCRYPTION_KEY`. Un opérateur suivant le message définirait `DOCFLOW_ENCRYPTION_KEY`, **sans effet**.

## Impact

Diagnostic trompeur : l'opérateur configure la mauvaise variable et le chiffrement reste inopérant.

## Piste de correction

Aligner tous les messages sur `ENCRYPTION_KEY` (le nom réellement lu par `Settings`).

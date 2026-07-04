# DB-15 — Messages d'erreur citant `DOCFLOW_ENCRYPTION_KEY` au lieu de `ENCRYPTION_KEY`

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet. Messages d'erreur applicatifs
> (`vault/router.py`, `webhooks/service.py`) alignés sur `ENCRYPTION_KEY`. Les commentaires
> dans `migrations/0012_vault_wallets.sql` et `migrations/0017_user_secrets.sql` n'ont
> **pas** été touchés : CLAUDE.md interdit d'éditer une migration déjà appliquée, même
> pour un commentaire — une migration corrective devrait porter ce correctif cosmétique
> si jugé nécessaire.

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

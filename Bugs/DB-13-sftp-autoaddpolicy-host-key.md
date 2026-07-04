# DB-13 — SFTP : `AutoAddPolicy`, host key jamais vérifiée

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR (sécurité : MITM sur l'upload du dump)
- **Confiance** : haute (signalé par deux revues)
- **Zone** : backup / db_dump
- **Fichiers** : `backend/src/docflow/backup/db_dump.py:75`

## Description

`ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())` accepte **n'importe quelle** clé d'hôte. Le dump **complet** de la base (tous workspaces, secrets chiffrés inclus) peut être uploadé vers un serveur usurpé (MITM/DNS spoof) sans aucune alerte.

## Impact

Exfiltration possible du dump complet vers un hôte usurpé.

## Piste de correction

Stocker/valider le fingerprint de l'hôte (le champ `fingerprint` existe déjà dans `remote_certificate`) ; utiliser `RejectPolicy` avec `load_host_keys` (TOFU au premier enregistrement).

# DB-10 — FTPS : port par défaut 990 incompatible avec le TLS explicite

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : backup / db_dump
- **Fichiers** : `backend/src/docflow/backup/db_dump.py:14, 49-54`

## Description

`_DEFAULT_PORTS = {"ftps": 990}` mais `ftplib.FTP_TLS` ne fait que du TLS **explicite** (connexion claire puis `AUTH TLS`), typiquement port 21. Sur 990, le serveur attend un handshake TLS immédiat → la connexion claire de `ftp.connect` pend jusqu'au timeout (60 s) ou échoue.

## Scénario de reproduction

1. Configurer un remote FTPS sans port explicite.
2. Le job de backup pend puis échoue au timeout à chaque exécution.

## Impact

Un point FTPS sans port explicite ne peut **jamais** fonctionner.

## Piste de correction

Défaut 21 pour ftps (TLS explicite), ou implémenter le TLS implicite (wrap du socket avant le dialogue) si 990 est visé.

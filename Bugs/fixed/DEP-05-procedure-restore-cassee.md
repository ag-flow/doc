# DEP-05 — Procédure de restauration DEPLOY.md non fonctionnelle/destructrice

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : déploiement / doc backup-restore
- **Fichiers** : `deploy/DEPLOY.md:114-138`

## Description

Le backup documenté est un dump plain SQL **sans `--clean`**. La restauration documentée le rejoue via `psql` **dans la base existante non vidée**, **sans `-v ON_ERROR_STOP=1`**. Chaque `CREATE TABLE` échoue en « already exists », `psql` continue, les `COPY` échouent ou dupliquent selon les contraintes, et la commande se termine avec un **air de succès**.

## Scénario de reproduction

1. Incident.
2. L'opérateur suit la doc à la lettre.
3. Base dans un état mélangé ancien/nouveau, sans erreur bloquante visible.

## Impact

Une restauration crue selon la doc corrompt silencieusement la base au lieu de la restaurer.

## Piste de correction

Documenter `pg_dump --clean --if-exists` (ou drop/recreate de la base avant restore) + `psql -v ON_ERROR_STOP=1`, et arrimer la doc sur la feature interne de backup (format custom + `pg_restore`).

# DB-14 — `apply()` sans verrou : course entre instances au boot

- **Gravité** : 🟡 MINEUR (déploiement mono-instance actuel)
- **Confiance** : haute
- **Zone** : db / apply (runner de migrations)
- **Fichiers** : `backend/src/docflow/db/apply.py:28-49`

## Description

La lecture de `schema_migrations` et l'application se font dans des connexions/transactions séparées, **sans `pg_advisory_lock`**. Deux instances démarrant en même temps appliquent la même migration ; la seconde échoue (PK sur `version` → rollback, DB cohérente) mais **crashe au démarrage**.

## Scénario de reproduction

Démarrer deux instances simultanément sur une base avec une migration en attente → l'une des deux crashe au boot.

## Impact

Crash de démarrage en scénario multi-instance (pertinent si l'on scale un jour horizontalement).

## Piste de correction

`SELECT pg_advisory_lock(<clé>)` en tête d'`apply`, libéré à la fin.

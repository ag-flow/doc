# DB-09 — Job en échec : retry toutes les 30 s au lieu de l'intervalle configuré

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : backup / worker
- **Fichiers** : `backend/src/docflow/backup/worker.py:20-27, 254-256`

## Description

`_due_jobs` calcule `last_run_at` sur les seuls runs `status='success'`. Pour un job à intervalle (`schedule_every_seconds`), tant qu'aucun run ne réussit, `elapsed` reste dépassé → le job est relancé **à chaque tick (30 s)**.

## Scénario de reproduction

1. Job quotidien vers un remote temporairement injoignable.
2. 2 880 tentatives/jour, spam de runs en erreur dans `backup_job_run`, hammering du remote.

## Impact

Tempête de tentatives (charge CPU/réseau, spam de logs, lockout possible d'un compte FTP/PAT distant).

## Piste de correction

Baser `_is_due` sur le **dernier run toutes natures confondues** (ou un backoff explicite), en gardant le curseur incrémental sur le dernier succès.

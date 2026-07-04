# DB-08 — Run `running` orphelin après crash → job bloqué définitivement

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : backup / worker
- **Fichiers** : `backend/src/docflow/backup/worker.py:149-150, 257-258, 265` ; `backup/service.py` (`start_run`)

## Description

`start_run` insère un run `status='running'` ; `_due_jobs` exclut tout job avec `running_count > 0`. Si le process crashe/redémarre (deploy, OOM) entre `start_run` et `finish_run`, le run reste `running` **pour toujours** : aucun code (ni au boot du worker, ni ailleurs) ne réconcilie les runs orphelins.

## Scénario de reproduction

1. Redéploiement via `dev-deploy.sh` pendant un dump d'1 h.
2. Le run reste `running` en base.
3. Le job n'est **plus jamais** planifié, sans erreur visible, jusqu'à un `UPDATE` manuel.

## Impact

Un job de backup peut mourir définitivement après un simple redéploiement.

## Piste de correction

Au démarrage de `worker_loop`, marquer `error` tous les runs `running` (ou ceux plus vieux qu'un TTL).

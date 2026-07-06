# DB-05 — `croniter` absent des dépendances → jobs cron jamais exécutés

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute (vérifié : `import croniter` → `ModuleNotFoundError`)
- **Zone** : backup / scheduler
- **Fichiers** : `backend/src/docflow/backup/worker.py:28-34` ; `backend/pyproject.toml`

## Description

`_is_due` importe `croniter` dans un try/except `ImportError` qui ne fait qu'un `log.warning`. La dépendance **n'est pas déclarée**. Un job planifié en cron (`0 3 * * *`) ne s'exécute **jamais**, silencieusement (un warning toutes les 30 s dans les logs, aucun run en erreur visible côté UI).

Bug latent associé : une fois croniter installé, `croniter.match(cron, now)` est vrai pendant **toute la minute** et le tick est de 30 s sans comparaison au dernier run → un job cron se déclenche **deux fois** dans la minute correspondante.

## Scénario de reproduction

1. Créer un job de backup planifié en cron.
2. Attendre l'heure prévue → aucun run n'est jamais créé.

## Impact

Toute planification cron des sauvegardes est inopérante, sans erreur visible.

## Piste de correction

Ajouter `croniter` au `pyproject.toml`, et dans `_is_due` (branche cron) vérifier que `last_run_at` est antérieur à la dernière occurrence cron pour éviter le double déclenchement.

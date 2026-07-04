# DB-06 — `pg_dump` : mot de passe Postgres visible dans `ps` (argv)

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute (signalé par deux revues)
- **Zone** : backup / db_dump
- **Fichiers** : `backend/src/docflow/backup/db_dump.py:25`

## Description

```python
cmd = ["pg_dump", ..., f"--dbname={database_url}"]
```

`database_url` est le DSN complet `postgresql://user:password@host/db`. Le mot de passe est dans l'**argv** du process `pg_dump`, lisible dans `/proc/*/cmdline` / `ps aux` par tout process du conteneur — **et sur l'hôte** (les processus conteneurisés partagent le noyau) — pendant toute la durée du dump (timeout jusqu'à 3600 s).

## Scénario de reproduction

1. Un job de backup est lancé.
2. N'importe quel utilisateur non privilégié de l'hôte fait `ps aux | grep pg_dump`.
3. Il récupère le mot de passe de la base.

## Impact

Fuite du mot de passe Postgres à tout observateur local pendant chaque dump.

## Piste de correction

Passer un DSN **sans** mot de passe dans l'argv et injecter le mot de passe via l'env `PGPASSWORD` (ou `~/.pgpass`) dans `subprocess.run`.

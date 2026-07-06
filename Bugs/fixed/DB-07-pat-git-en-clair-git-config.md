# DB-07 — PAT git persisté en clair dans `.git/config`
> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : backup / git_sync
- **Fichiers** : `backend/src/docflow/backup/worker.py:93` ; `backup/git_sync.py:234`

## Description

```python
remote_url = f"https://{username}:{secret}@{base_url}"
Repo.clone_from(remote_url, ...)
```

Le token est (a) écrit **en clair et de façon permanente** dans `/data/backup-repos/{job_id}/.git/config` (URL du remote `origin`), (b) visible dans l'argv de `git clone` pendant son exécution. Le projet stocke pourtant ce secret **chiffré Fernet** en base — le déchiffré atterrit en clair sur disque.

*(Note : GitPython 3.1.50 redacte bien les credentials dans les messages `GitCommandError`, donc pas de fuite via `error_message`/logs par ce chemin.)*

## Scénario de reproduction

1. Un job git_sync HTTPS avec PAT s'exécute.
2. `cat /data/backup-repos/{job_id}/.git/config` → le PAT en clair.

## Impact

Fuite persistante du token git (accès en écriture au repo distant) sur le volume de données.

## Piste de correction

URL sans credentials + credential helper éphémère (helper en config locale pointant sur un store mémoire), ou `http.extraHeader` passé par env, ou au minimum réécrire l'URL du remote sans secret après clone et injecter le token à chaque fetch/push.

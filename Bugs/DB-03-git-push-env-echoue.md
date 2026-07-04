# DB-03 — `origin.push(env=)` fait échouer tous les push git

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🔴 CRITIQUE
- **Confiance** : haute (vérifié sur GitPython 3.1.50 installé)
- **Zone** : backup / git_sync
- **Fichiers** : `backend/src/docflow/backup/git_sync.py:276` (+ `234`)

## Description

`git.Remote.push` n'a **pas** de paramètre `env` (GitPython 3.1.50). Le kwarg part dans `**kwargs` → `transform_kwarg` → argument CLI `--env={...}` (généré même pour `env={}`, car `{}` n'est ni `False` ni `None`). `git push --env=...` → « unknown option ». Tout push échoue ; le commit local existe mais n'est jamais poussé, le run passe en erreur.

Bug associé : dans la branche clone (l.234), `env` est correctement passé à `clone_from`, mais le `Repo` retourné n'hérite pas de cet env — même corrigé, un push SSH après un clone frais n'aurait pas `GIT_SSH_COMMAND`.

## Scénario de reproduction

N'importe quel run git_sync avec des changements → commit local OK → push → `GitCommandError` → `RuntimeError("git push échoué")`.

## Impact

La sauvegarde git_sync ne pousse **jamais** rien sur le remote. Fonctionnalité entièrement non opérationnelle.

## Piste de correction

`repo.git.update_environment(**env)` systématiquement après obtention du repo (pull **et** clone), et `origin.push(git_branch)` **sans** kwarg `env`.

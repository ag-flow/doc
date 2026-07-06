# DB-11 — URL SSH git malformée (`git@host/repo` au lieu de `:`)

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟠 MAJEUR
- **Confiance** : haute
- **Zone** : backup / git_sync (auth certificate)
- **Fichiers** : `backend/src/docflow/backup/worker.py:50-58, 72`

## Description

Pour `auth_type='certificate'`, `remote_url = f"git@{base_url}"` où `base_url = "github.com/{repo}.git"` → `git@github.com/org/repo.git`. **Sans `:` après le host**, git ne reconnaît pas la syntaxe scp-like et traite la chaîne comme un **chemin local** → clone échoue toujours (« repository does not exist »).

## Scénario de reproduction

Configurer un remote git_sync SSH (certificat) → tout clone échoue avec « repository does not exist ».

## Impact

L'auth SSH par certificat est entièrement non fonctionnelle pour git_sync.

## Piste de correction

`git@{host}:{repo}.git` (ou `ssh://git@{host}/{repo}.git`).

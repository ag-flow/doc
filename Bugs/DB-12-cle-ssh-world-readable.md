# DB-12 — Clé privée SSH : fenêtre world-readable, jamais supprimée

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Sonnet.

- **Gravité** : 🟡 MINEUR
- **Confiance** : haute
- **Zone** : backup / worker
- **Fichiers** : `backend/src/docflow/backup/worker.py:68-71, 116-119`

## Description

`key_path.write_text(private_key)` crée le fichier avec l'umask (typiquement 644) **avant** `chmod(0o600)` — fenêtre world-readable. La clé déchiffrée reste ensuite **indéfiniment** sur disque dans `/data/backup-repos/keys/`. Ces écritures se font directement dans une fonction async (event loop bloqué brièvement).

## Impact

Exposition transitoire (world-readable) puis persistante d'une clé privée SSH sur le volume de données.

## Piste de correction

`os.open(..., O_WRONLY|O_CREAT, 0o600)` (permissions dès la création), suppression après usage (ou tmpfs), et exécution via `asyncio.to_thread`.

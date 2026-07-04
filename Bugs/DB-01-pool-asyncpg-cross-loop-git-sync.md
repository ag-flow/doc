# DB-01 — Pool asyncpg utilisé depuis un autre event loop (git_sync)

> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Fable.

- **Gravité** : 🔴 CRITIQUE
- **Confiance** : haute
- **Zone** : backup / git_sync
- **Fichiers** : `backend/src/docflow/backup/worker.py:165-181`

## Description

`_run_job` exécute :

```python
run_in_executor(None, lambda: asyncio.run(run_git_sync(pool, ...)))
```

`run_git_sync` fait `pool.acquire()` et des requêtes sur un pool **créé et peuplé dans le loop principal**, mais depuis un **nouveau** loop dans un thread executor. Un pool asyncpg est lié à son loop (`self._loop` capturé à la création, connexions/transports enregistrés sur le loop principal) ; l'utiliser cross-loop/cross-thread n'est pas supporté.

## Scénario de reproduction

1. L'app tourne ; le loop principal a déjà mis des connexions en idle dans le pool (n'importe quelle requête API).
2. Un job `git_sync` devient dû → le thread executor récupère une connexion liée au loop principal.
3. `RuntimeError: ... attached to a different loop`, ou corruption d'état non déterministe (futures réveillés depuis le mauvais thread).

## Impact

Le git_sync échoue (run en `error`) ou, pire, corrompt silencieusement l'état du pool partagé avec l'API.

## Piste de correction

Ne pas wrapper dans `asyncio.run`. Séparer `run_git_sync` en (a) phase DB async exécutée dans le loop principal, (b) phase git purement bloquante passée à `asyncio.to_thread`. C'est déjà le pattern correct de `run_db_dump`.

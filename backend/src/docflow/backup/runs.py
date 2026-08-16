"""Cycle de vie des exécutions (`backup_job_run`) : historique, lifecycle, déclenchement manuel.

Séparé de `service.py` (CRUD des jobs) pour respecter la limite de 300 lignes
par fichier et isoler deux responsabilités distinctes : définir un job vs.
tracer/déclencher ses exécutions.
"""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
from fastapi import HTTPException

from docflow.backup.schemas import BackupJobRunOut

RUN_RETENTION = 15  # nombre de runs conservés par job — les plus anciens sont purgés

# Référence forte sur les tasks de run déclenchées manuellement : asyncio ne
# garde qu'une référence faible sur les tasks créées par create_task, un objet
# non référencé ailleurs peut être ramassé par le GC avant son exécution.
_background_tasks: set[asyncio.Task[None]] = set()


def _run_row(row: asyncpg.Record) -> BackupJobRunOut:
    return BackupJobRunOut(**dict(row))


# ── Historique d'exécution ────────────────────────────────────────────────────


async def list_runs(
    pool: asyncpg.Pool, job_slug: str, limit: int = RUN_RETENTION
) -> list[BackupJobRunOut]:
    async with pool.acquire() as conn:
        jid: uuid.UUID | None = await conn.fetchval(
            "SELECT id FROM backup_job WHERE slug = $1", job_slug
        )
        if jid is None:
            raise HTTPException(404, "job introuvable")
        rows = await conn.fetch(
            """
            SELECT id, job_id, started_at, finished_at, status, error_message,
                   last_change_seq, files_written, files_deleted, commit_sha
            FROM backup_job_run WHERE job_id = $1
            ORDER BY started_at DESC LIMIT $2
            """,
            jid,
            limit,
        )
    return [_run_row(r) for r in rows]


# ── Lifecycle run (appelé par le worker) ─────────────────────────────────────


async def reconcile_orphan_runs(pool: asyncpg.Pool) -> int:
    """Marque en erreur tout run resté `running` (orphelin après crash/redéploiement).

    Sans cela, `_due_jobs` exclut indéfiniment tout job dont le dernier run est
    resté `running` — le job ne serait plus jamais planifié. À appeler une fois
    au démarrage du worker, avant toute planification.
    """
    result: str = await pool.execute(
        """
        UPDATE backup_job_run
        SET finished_at = now(), status = 'error',
            error_message = 'run orphelin réconcilié au démarrage du worker'
        WHERE status = 'running'
        """
    )
    return int(result.split()[-1])


async def start_run(conn: asyncpg.Connection, job_id: uuid.UUID) -> uuid.UUID:
    run_id: uuid.UUID = await conn.fetchval(
        "INSERT INTO backup_job_run (job_id) VALUES ($1) RETURNING id", job_id
    )
    return run_id


async def prune_old_runs(
    conn: asyncpg.Connection, job_id: uuid.UUID, *, keep: int = RUN_RETENTION
) -> None:
    """Ne conserve que les `keep` runs les plus récents d'un job — purge les plus anciens.

    À appeler après chaque finish_run : l'historique ne doit pas croître sans borne.
    """
    await conn.execute(
        """
        DELETE FROM backup_job_run
        WHERE job_id = $1
          AND id NOT IN (
              SELECT id FROM backup_job_run
              WHERE job_id = $1
              ORDER BY started_at DESC
              LIMIT $2
          )
        """,
        job_id,
        keep,
    )


async def finish_run(
    conn: asyncpg.Connection,
    run_id: uuid.UUID,
    *,
    status: str,
    error_message: str | None = None,
    last_change_seq: int | None = None,
    files_written: int | None = None,
    files_deleted: int | None = None,
    commit_sha: str | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE backup_job_run SET
            finished_at=now(), status=$2, error_message=$3,
            last_change_seq=$4, files_written=$5, files_deleted=$6, commit_sha=$7
        WHERE id=$1
        """,
        run_id,
        status,
        error_message,
        last_change_seq,
        files_written,
        files_deleted,
        commit_sha,
    )


# ── Déclenchement manuel (endpoint API / automation) ──────────────────────────

_TRIGGER_JOB_SELECT = """
    SELECT j.id, j.slug, j.strategy, j.git_base_path,
           j.workspace_technical_key AS workspace_id, w.slug AS workspace_slug,
           j.data_block_ref AS data_block_id,
           rp.slug AS remote_point_slug,
           (SELECT COUNT(*) FROM backup_job_run r
            WHERE r.job_id = j.id AND r.status = 'running') AS running_count
    FROM backup_job j
    JOIN remote_point rp ON rp.id = j.remote_point_id
    LEFT JOIN workspace w ON w.workspace_technical_key = j.workspace_technical_key
    WHERE j.slug = $1
"""


async def trigger_run_now(pool: asyncpg.Pool, settings: object, job_slug: str) -> BackupJobRunOut:
    """Déclenche un run immédiat, hors planification.

    Point d'entrée du endpoint `POST /admin/backup/jobs/{slug}/run`, appelable
    par une automation via l'API (référencé comme opération de contrat). Refuse
    si un run est déjà `running` sur ce job (même garde que le scheduler).
    Asynchrone : le run s'exécute en tâche de fond, l'appelant consulte
    `list_runs` pour le résultat.
    """
    from docflow.backup.worker import run_job

    row = await pool.fetchrow(_TRIGGER_JOB_SELECT, job_slug)
    if row is None:
        raise HTTPException(404, "job introuvable")
    if row["running_count"] > 0:
        raise HTTPException(409, "un run est déjà en cours pour ce job")

    job = dict(row)
    async with pool.acquire() as conn:
        run_id = await start_run(conn, job["id"])

    task = asyncio.create_task(run_job(pool, job, settings, run_id=run_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    run_row = await pool.fetchrow(
        """
        SELECT id, job_id, started_at, finished_at, status, error_message,
               last_change_seq, files_written, files_deleted, commit_sha
        FROM backup_job_run WHERE id = $1
        """,
        run_id,
    )
    assert run_row is not None
    return _run_row(run_row)

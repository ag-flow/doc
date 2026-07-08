from __future__ import annotations

import asyncio
import uuid

import asyncpg
from fastapi import HTTPException

from docflow.backup.schemas import (
    BackupJobCreate,
    BackupJobOut,
    BackupJobRunOut,
    BackupJobUpdate,
    DumpArchiveOut,
)


def _job_row(row: asyncpg.Record) -> BackupJobOut:
    return BackupJobOut(**dict(row))


def _run_row(row: asyncpg.Record) -> BackupJobRunOut:
    return BackupJobRunOut(**dict(row))


_JOB_SELECT = """
    SELECT j.id, j.slug, j.label, j.strategy, j.enabled,
           rp.slug AS remote_point_slug,
           j.workspace_technical_key AS workspace_id,
           w.slug AS workspace_slug,
           j.schedule_cron, j.schedule_every_seconds, j.git_base_path,
           j.created_at, j.updated_at,
           (SELECT r.started_at FROM backup_job_run r
            WHERE r.job_id = j.id ORDER BY r.started_at DESC LIMIT 1) AS last_run_at,
           (SELECT r.status FROM backup_job_run r
            WHERE r.job_id = j.id ORDER BY r.started_at DESC LIMIT 1) AS last_run_status
    FROM backup_job j
    JOIN remote_point rp ON rp.id = j.remote_point_id
    LEFT JOIN workspace w ON w.workspace_technical_key = j.workspace_technical_key
"""


async def _resolve_remote_point(conn: asyncpg.Connection, slug: str) -> uuid.UUID:
    pid: uuid.UUID | None = await conn.fetchval("SELECT id FROM remote_point WHERE slug = $1", slug)
    if pid is None:
        raise HTTPException(422, f"remote point '{slug}' introuvable")
    return pid


async def _resolve_workspace(conn: asyncpg.Connection, slug: str | None) -> uuid.UUID | None:
    if slug is None:
        return None
    wid: uuid.UUID | None = await conn.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", slug
    )
    if wid is None:
        raise HTTPException(422, f"workspace '{slug}' introuvable")
    return wid


# ── CRUD jobs ─────────────────────────────────────────────────────────────────


async def list_jobs(pool: asyncpg.Pool) -> list[BackupJobOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_JOB_SELECT + " ORDER BY j.created_at")
    return [_job_row(r) for r in rows]


async def create_job(pool: asyncpg.Pool, body: BackupJobCreate) -> BackupJobOut:
    async with pool.acquire() as conn:
        rp_id = await _resolve_remote_point(conn, body.remote_point_slug)
        ws_id = await _resolve_workspace(conn, body.workspace_slug)
        try:
            await conn.execute(
                """
                INSERT INTO backup_job
                    (slug, label, strategy, enabled, remote_point_id,
                     workspace_technical_key, schedule_cron, schedule_every_seconds,
                     git_base_path)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                """,
                body.slug,
                body.label,
                body.strategy,
                body.enabled,
                rp_id,
                ws_id,
                body.schedule_cron,
                body.schedule_every_seconds,
                body.git_base_path,
            )
        except asyncpg.UniqueViolationError as e:
            raise HTTPException(409, "slug de job déjà utilisé") from e
        row = await conn.fetchrow(_JOB_SELECT + " WHERE j.slug = $1", body.slug)
    assert row is not None
    return _job_row(row)


async def get_job(pool: asyncpg.Pool, slug: str) -> BackupJobOut:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_JOB_SELECT + " WHERE j.slug = $1", slug)
    if row is None:
        raise HTTPException(404, "job introuvable")
    return _job_row(row)


async def update_job(pool: asyncpg.Pool, slug: str, body: BackupJobUpdate) -> BackupJobOut:
    async with pool.acquire() as conn:
        jid: uuid.UUID | None = await conn.fetchval(
            "SELECT id FROM backup_job WHERE slug = $1", slug
        )
        if jid is None:
            raise HTTPException(404, "job introuvable")
        rp_id = await _resolve_remote_point(conn, body.remote_point_slug)
        ws_id = await _resolve_workspace(conn, body.workspace_slug)
        await conn.execute(
            """
            UPDATE backup_job SET
                label=$2, enabled=$3, remote_point_id=$4,
                workspace_technical_key=$5, schedule_cron=$6,
                schedule_every_seconds=$7, git_base_path=$8, updated_at=now()
            WHERE slug=$1
            """,
            slug,
            body.label,
            body.enabled,
            rp_id,
            ws_id,
            body.schedule_cron,
            body.schedule_every_seconds,
            body.git_base_path,
        )
        row = await conn.fetchrow(_JOB_SELECT + " WHERE j.slug = $1", slug)
    assert row is not None
    return _job_row(row)


async def delete_job(pool: asyncpg.Pool, slug: str) -> None:
    async with pool.acquire() as conn:
        deleted = await conn.execute("DELETE FROM backup_job WHERE slug = $1", slug)
    if deleted == "DELETE 0":
        raise HTTPException(404, "job introuvable")


# ── Listing des archives sur le remote (jobs db_dump) ─────────────────────────

_DUMP_DEFAULT_PORTS = {"ftp": 21, "ftps": 21, "sftp": 22}


async def list_job_archives(
    pool: asyncpg.Pool, settings: object, job_slug: str
) -> list[DumpArchiveOut]:
    """Liste les archives de dump d'un job db_dump sur son remote point.

    Read-only : ouvre une connexion ftp/ftps/sftp, énumère le répertoire de
    dépôt (git_base_path du job), ne retient que les fichiers suivant la
    convention de nommage, triés du plus récent au plus ancien. La clé privée
    éventuellement déchiffrée est effacée du disque en fin d'appel.
    """
    from docflow.backup import archives
    from docflow.remote.connection import delete_key_file, resolve_dump_auth

    job = await get_job(pool, job_slug)
    if job.strategy != "db_dump":
        raise HTTPException(422, "listing d'archives réservé aux jobs db_dump")

    async with pool.acquire() as conn:
        point_type: str | None = await conn.fetchval(
            "SELECT point_type FROM remote_point WHERE slug = $1", job.remote_point_slug
        )
    if point_type not in ("ftp", "ftps", "sftp"):
        raise HTTPException(422, f"type de point non supporté pour le listing : {point_type!r}")

    host, port, username, password, ssh_key_path = await resolve_dump_auth(
        pool, job.remote_point_slug, settings
    )
    eff_port = port or _DUMP_DEFAULT_PORTS[point_type]
    try:
        if point_type == "sftp":
            raw = await asyncio.to_thread(
                archives.list_sftp_archives,
                host=host,
                port=eff_port,
                username=username,
                password=password,
                ssh_key_path=ssh_key_path,
                remote_dir=job.git_base_path,
            )
        else:
            if not password:
                raise HTTPException(422, f"mot de passe requis pour {point_type.upper()}")
            raw = await asyncio.to_thread(
                archives.list_ftp_archives,
                host=host,
                port=eff_port,
                username=username,
                password=password,
                remote_dir=job.git_base_path,
                tls=(point_type == "ftps"),
            )
    finally:
        if ssh_key_path:
            await asyncio.to_thread(delete_key_file, ssh_key_path)

    raw.sort(key=lambda a: a["created_at"], reverse=True)
    return [DumpArchiveOut(**a) for a in raw]


# ── Historique d'exécution ────────────────────────────────────────────────────

RUN_RETENTION = 15  # nombre de runs conservés par job — les plus anciens sont purgés


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

from __future__ import annotations

import asyncio
import uuid

import asyncpg
from fastapi import HTTPException

from docflow.backup.schemas import (
    BackupJobCreate,
    BackupJobOut,
    BackupJobUpdate,
    DumpArchiveOut,
)


def _job_row(row: asyncpg.Record) -> BackupJobOut:
    return BackupJobOut(**dict(row))


_JOB_SELECT = """
    SELECT j.id, j.slug, j.label, j.strategy, j.enabled,
           rp.slug AS remote_point_slug,
           j.workspace_technical_key AS workspace_id,
           w.slug AS workspace_slug,
           db.slug AS data_block_slug,
           j.schedule_cron, j.schedule_every_seconds, j.git_base_path,
           j.created_at, j.updated_at,
           (SELECT r.started_at FROM backup_job_run r
            WHERE r.job_id = j.id ORDER BY r.started_at DESC LIMIT 1) AS last_run_at,
           (SELECT r.status FROM backup_job_run r
            WHERE r.job_id = j.id ORDER BY r.started_at DESC LIMIT 1) AS last_run_status
    FROM backup_job j
    JOIN remote_point rp ON rp.id = j.remote_point_id
    LEFT JOIN workspace w ON w.workspace_technical_key = j.workspace_technical_key
    LEFT JOIN data_block db ON db.id = j.data_block_ref
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


async def _resolve_data_block(
    conn: asyncpg.Connection, workspace_id: uuid.UUID | None, slug: str | None
) -> uuid.UUID | None:
    """Résout un bloc par slug, scopé au workspace du job.

    `workspace_id` est garanti non-None ici : la validation pydantic
    (BackupJobCreate/Update) impose déjà data_block_slug ⇒ workspace_slug.
    """
    if slug is None:
        return None
    assert workspace_id is not None
    bid: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = $2",
        workspace_id,
        slug,
    )
    if bid is None:
        raise HTTPException(422, f"bloc '{slug}' introuvable dans ce workspace")
    return bid


# ── CRUD jobs ─────────────────────────────────────────────────────────────────


async def list_jobs(pool: asyncpg.Pool) -> list[BackupJobOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_JOB_SELECT + " ORDER BY j.created_at")
    return [_job_row(r) for r in rows]


async def create_job(pool: asyncpg.Pool, body: BackupJobCreate) -> BackupJobOut:
    async with pool.acquire() as conn:
        rp_id = await _resolve_remote_point(conn, body.remote_point_slug)
        ws_id = await _resolve_workspace(conn, body.workspace_slug)
        block_id = await _resolve_data_block(conn, ws_id, body.data_block_slug)
        try:
            await conn.execute(
                """
                INSERT INTO backup_job
                    (slug, label, strategy, enabled, remote_point_id,
                     workspace_technical_key, data_block_ref, schedule_cron,
                     schedule_every_seconds, git_base_path)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                """,
                body.slug,
                body.label,
                body.strategy,
                body.enabled,
                rp_id,
                ws_id,
                block_id,
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
        block_id = await _resolve_data_block(conn, ws_id, body.data_block_slug)
        await conn.execute(
            """
            UPDATE backup_job SET
                label=$2, enabled=$3, remote_point_id=$4,
                workspace_technical_key=$5, data_block_ref=$6, schedule_cron=$7,
                schedule_every_seconds=$8, git_base_path=$9, updated_at=now()
            WHERE slug=$1
            """,
            slug,
            body.label,
            body.enabled,
            rp_id,
            ws_id,
            block_id,
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

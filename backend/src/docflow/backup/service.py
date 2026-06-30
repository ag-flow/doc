from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.backup.schemas import (
    BackupJobCreate,
    BackupJobOut,
    BackupJobRunOut,
    BackupJobUpdate,
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
    pid: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM remote_point WHERE slug = $1", slug
    )
    if pid is None:
        raise HTTPException(422, f"remote point '{slug}' introuvable")
    return pid


async def _resolve_workspace(
    conn: asyncpg.Connection, slug: str | None
) -> uuid.UUID | None:
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
                body.slug, body.label, body.strategy, body.enabled, rp_id,
                ws_id, body.schedule_cron, body.schedule_every_seconds,
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


async def update_job(
    pool: asyncpg.Pool, slug: str, body: BackupJobUpdate
) -> BackupJobOut:
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
            slug, body.label, body.enabled, rp_id,
            ws_id, body.schedule_cron, body.schedule_every_seconds,
            body.git_base_path,
        )
        row = await conn.fetchrow(_JOB_SELECT + " WHERE j.slug = $1", slug)
    assert row is not None
    return _job_row(row)


async def delete_job(pool: asyncpg.Pool, slug: str) -> None:
    async with pool.acquire() as conn:
        deleted = await conn.execute(
            "DELETE FROM backup_job WHERE slug = $1", slug
        )
    if deleted == "DELETE 0":
        raise HTTPException(404, "job introuvable")


# ── Historique d'exécution ────────────────────────────────────────────────────

async def list_runs(
    pool: asyncpg.Pool, job_slug: str, limit: int = 20
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
            jid, limit,
        )
    return [_run_row(r) for r in rows]


# ── Lifecycle run (appelé par le worker) ─────────────────────────────────────

async def start_run(conn: asyncpg.Connection, job_id: uuid.UUID) -> uuid.UUID:
    run_id: uuid.UUID = await conn.fetchval(
        "INSERT INTO backup_job_run (job_id) VALUES ($1) RETURNING id", job_id
    )
    return run_id


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
        run_id, status, error_message,
        last_change_seq, files_written, files_deleted, commit_sha,
    )

from __future__ import annotations

import asyncio
import pathlib
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
import structlog

from docflow.backup import service as svc
from docflow.remote.connection import delete_key_file, resolve_dump_auth, resolve_git_auth

log = structlog.get_logger(__name__)

_REPOS_ROOT = pathlib.Path("/data/backup-repos")
_TICK = 30  # secondes entre deux balayages du scheduler


def _is_due(job: dict[str, Any], now: datetime) -> bool:
    """Vérifie si un job doit être exécuté maintenant.

    `job["last_run_at"]` doit être le dernier run toutes natures confondues
    (succès **et** échec) : sinon, un job qui échoue en boucle n'a jamais de
    `last_run_at` et redéclenche à chaque tick au lieu de respecter
    l'intervalle configuré. Le curseur incrémental (`last_change_seq`), lui,
    reste basé sur le dernier succès (`_last_success_seq`).
    """
    last = job["last_run_at"]
    if job["schedule_every_seconds"]:
        if last is None:
            return True
        elapsed = (now - last.replace(tzinfo=UTC)).total_seconds()
        return bool(elapsed >= job["schedule_every_seconds"])
    if job["schedule_cron"]:
        try:
            from croniter import croniter  # type: ignore[import-untyped]
        except ImportError:
            log.warning("backup_cron_croniter_missing")
            return False
        if not croniter.match(job["schedule_cron"], now):
            return False
        if last is None:
            return True
        # `match` reste vrai pendant toute la minute : ne redéclencher que si
        # aucun run n'a déjà eu lieu depuis la dernière occurrence cron.
        prev_occurrence = croniter(job["schedule_cron"], now).get_prev(datetime)
        return bool(last.replace(tzinfo=UTC) < prev_occurrence)
    return False


_DUMPS_ROOT = pathlib.Path("/data/backup-dumps")


async def _run_job(pool: asyncpg.Pool, job: dict[str, Any], settings: object) -> None:
    job_id: uuid.UUID = job["id"]
    log.info("backup_job_start", job_slug=job["slug"], strategy=job["strategy"])

    async with pool.acquire() as conn:
        run_id = await svc.start_run(conn, job_id)

    ssh_key_path: str | None = None
    try:
        if job["strategy"] == "git_sync":
            remote_url, ssh_key_path, git_http_env = await resolve_git_auth(
                pool, job["remote_point_slug"], settings
            )
            point = await _get_point_detail(pool, job["remote_point_slug"])

            last_seq = await _last_success_seq(pool, job_id)
            ws_id = job.get("workspace_id")
            ws_slug = job.get("workspace_slug")

            from docflow.backup.git_sync import run_git_sync

            # `run_git_sync` est async et DOIT tourner dans le loop principal :
            # le pool asyncpg est lié à son event loop, l'utiliser depuis un
            # autre loop (asyncio.run dans un executor) corrompt son état.
            # La phase git bloquante est déportée en interne via
            # asyncio.to_thread — même découpage que run_db_dump.
            result = await run_git_sync(
                pool,
                job_id=job_id,
                workspace_technical_key=ws_id,
                workspace_slug=ws_slug,
                last_change_seq=last_seq,
                remote_url=remote_url,
                git_branch=point["git_branch"],
                git_base_path=job.get("git_base_path"),
                ssh_key_path=ssh_key_path,
                git_http_env=git_http_env,
                repos_root=_REPOS_ROOT,
            )
        else:
            host, port, username, password, ssh_key_path = await resolve_dump_auth(
                pool, job["remote_point_slug"], settings
            )
            point_detail = await _get_point_detail(pool, job["remote_point_slug"])
            db_url: str = getattr(settings, "database_url", "")
            if not db_url:
                raise RuntimeError("DATABASE_URL non configurée")

            from docflow.backup.db_dump import run_db_dump

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: run_db_dump(
                    job_id=job_id,
                    workspace_slug=job.get("workspace_slug"),
                    database_url=db_url,
                    point_type=point_detail["point_type"],
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    ssh_key_path=ssh_key_path,
                    remote_dir=job.get("git_base_path"),
                    dumps_root=_DUMPS_ROOT,
                ),
            )

        async with pool.acquire() as conn:
            await svc.finish_run(
                conn,
                run_id,
                status="success",
                last_change_seq=result["last_change_seq"],
                files_written=result["files_written"],
                files_deleted=result["files_deleted"],
                commit_sha=result["commit_sha"],
            )
        log.info("backup_job_success", job_slug=job["slug"], **result)

    except Exception as exc:
        log.error("backup_job_error", job_slug=job["slug"], error=str(exc))
        async with pool.acquire() as conn:
            await svc.finish_run(conn, run_id, status="error", error_message=str(exc))
    finally:
        # La clé privée déchiffrée ne doit jamais rester sur disque au-delà du run.
        if ssh_key_path:
            await asyncio.to_thread(delete_key_file, ssh_key_path)


async def _last_success_seq(pool: asyncpg.Pool, job_id: uuid.UUID) -> int:
    seq: int | None = await pool.fetchval(
        """
        SELECT last_change_seq FROM backup_job_run
        WHERE job_id = $1 AND status = 'success' AND last_change_seq IS NOT NULL
        ORDER BY started_at DESC LIMIT 1
        """,
        job_id,
    )
    return seq or 0


async def _get_point_detail(pool: asyncpg.Pool, slug: str) -> dict[str, Any]:
    row = await pool.fetchrow(
        "SELECT point_type, git_branch FROM remote_point WHERE slug = $1", slug
    )
    assert row is not None
    return dict(row)


async def _due_jobs(pool: asyncpg.Pool, now: datetime) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT j.id, j.slug, j.strategy, j.schedule_cron, j.schedule_every_seconds,
               j.git_base_path, j.workspace_technical_key AS workspace_id,
               w.slug AS workspace_slug,
               rp.slug AS remote_point_slug,
               (SELECT r.started_at FROM backup_job_run r
                WHERE r.job_id = j.id
                ORDER BY r.started_at DESC LIMIT 1) AS last_run_at,
               (SELECT COUNT(*) FROM backup_job_run r
                WHERE r.job_id = j.id AND r.status = 'running') AS running_count
        FROM backup_job j
        JOIN remote_point rp ON rp.id = j.remote_point_id
        LEFT JOIN workspace w ON w.workspace_technical_key = j.workspace_technical_key
        WHERE j.enabled = true
        """
    )
    return [dict(r) for r in rows if r["running_count"] == 0 and _is_due(dict(r), now)]


async def worker_loop(pool: asyncpg.Pool, settings: object) -> None:
    _REPOS_ROOT.mkdir(parents=True, exist_ok=True)
    _DUMPS_ROOT.mkdir(parents=True, exist_ok=True)
    reconciled = await svc.reconcile_orphan_runs(pool)
    if reconciled:
        log.warning("backup_orphan_runs_reconciled", count=reconciled)
    log.info("backup_worker_started")
    while True:
        try:
            now = datetime.now(tz=UTC)
            jobs = await _due_jobs(pool, now)
            for job in jobs:
                asyncio.create_task(_run_job(pool, job, settings))
        except Exception:
            log.exception("backup_worker_tick_error")
        await asyncio.sleep(_TICK)

from __future__ import annotations

import asyncio
import pathlib
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
import structlog

from docflow.backup import service as svc

log = structlog.get_logger(__name__)

_REPOS_ROOT = pathlib.Path("/data/backup-repos")
_TICK = 30  # secondes entre deux balayages du scheduler


def _is_due(job: dict[str, Any], now: datetime) -> bool:
    """Vérifie si un job doit être exécuté maintenant."""
    last = job["last_run_at"]
    if job["schedule_every_seconds"]:
        if last is None:
            return True
        elapsed = (now - last.replace(tzinfo=UTC)).total_seconds()
        return bool(elapsed >= job["schedule_every_seconds"])
    if job["schedule_cron"]:
        try:
            from croniter import croniter  # type: ignore[import-untyped]
            return bool(croniter.match(job["schedule_cron"], now))
        except ImportError:
            log.warning("backup_cron_croniter_missing")
    return False


async def _resolve_git_auth(
    pool: asyncpg.Pool, remote_point_slug: str, settings: object
) -> tuple[str, str | None]:
    """Retourne (remote_url, ssh_key_path | None)."""
    from docflow.remote import service as rp_svc

    fernet_key_obj = getattr(settings, "encryption_key", None)
    fernet_key: str | None = fernet_key_obj.reveal() if fernet_key_obj else None
    harpocrate_url: str | None = getattr(settings, "harpocrate_url", None)

    point = await rp_svc.get_point(pool, remote_point_slug)

    # Construction de l'URL distante
    provider = point.git_provider or "custom"
    host = point.host
    repo = point.git_repo or ""
    if provider == "github":
        base_url = f"github.com/{repo}.git"
    elif provider == "gitlab":
        base_url = f"gitlab.com/{repo}.git"
    else:
        base_url = f"{host}/{repo}.git"

    if point.auth_type == "certificate":
        # SSH — clé privée déchiffrée et écrite dans un fichier temporaire
        if not fernet_key:
            raise RuntimeError("encryption_key non configurée")
        assert point.certificate_slug
        private_key = await rp_svc.get_certificate_private_key(
            pool, point.certificate_slug, fernet_key
        )
        key_path = _REPOS_ROOT / "keys" / f"{point.certificate_slug}.pem"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(private_key)
        key_path.chmod(0o600)
        remote_url = f"git@{base_url}"
        return remote_url, str(key_path)

    # PAT : HTTPS avec token dans l'URL
    secret: str
    if point.auth_storage == "vault":
        from docflow.secrets.resolver import resolve
        from docflow.secrets.secret import Secret
        enc_key_obj = getattr(settings, "encryption_key", None)
        enc_key: str | None = enc_key_obj.reveal() if enc_key_obj else None
        secret = await resolve(
            Secret(point.auth_vault_ref or ""),
            harpocrate_url=harpocrate_url,
            pool=pool,
            enc_key=enc_key,
        )
    else:
        if not fernet_key:
            raise RuntimeError("encryption_key non configurée")
        secret = await rp_svc.get_point_secret(pool, remote_point_slug, fernet_key)

    remote_url = f"https://{point.username}:{secret}@{base_url}"
    return remote_url, None


async def _run_job(pool: asyncpg.Pool, job: dict[str, Any], settings: object) -> None:
    job_id: uuid.UUID = job["id"]
    log.info("backup_job_start", job_slug=job["slug"], strategy=job["strategy"])

    async with pool.acquire() as conn:
        run_id = await svc.start_run(conn, job_id)

    try:
        if job["strategy"] == "git_sync":
            remote_url, ssh_key_path = await _resolve_git_auth(
                pool, job["remote_point_slug"], settings
            )
            point = await _get_point_detail(pool, job["remote_point_slug"])

            last_seq = await _last_success_seq(pool, job_id)
            ws_id = job.get("workspace_id")
            ws_slug = job.get("workspace_slug")

            from docflow.backup.git_sync import run_git_sync

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: asyncio.run(
                    run_git_sync(
                        pool,
                        job_id=job_id,
                        workspace_technical_key=ws_id,
                        workspace_slug=ws_slug,
                        last_change_seq=last_seq,
                        remote_url=remote_url,
                        git_branch=point["git_branch"],
                        git_base_path=job.get("git_base_path"),
                        ssh_key_path=ssh_key_path,
                        repos_root=_REPOS_ROOT,
                    )
                ),
            )
        else:
            raise NotImplementedError("db_dump non encore implémenté")

        async with pool.acquire() as conn:
            await svc.finish_run(
                conn, run_id,
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
        "SELECT git_branch FROM remote_point WHERE slug = $1", slug
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
                WHERE r.job_id = j.id AND r.status = 'success'
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

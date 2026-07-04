from __future__ import annotations

import asyncio
import base64
import os
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


def _write_private_key(key_path: pathlib.Path, private_key: str) -> None:
    """Écrit la clé privée SSH déchiffrée avec permissions 0600 dès la création.

    `write_text` puis `chmod` laisse une fenêtre world-readable (permissions
    umask, typiquement 644) entre la création et le chmod : on ouvre le
    fichier directement avec le mode final via `os.open`.
    """
    key_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(private_key)


def _delete_key_file(key_path: str) -> None:
    """Supprime la clé privée temporaire — ne doit jamais rester sur disque après usage."""
    pathlib.Path(key_path).unlink(missing_ok=True)


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


async def _resolve_git_auth(
    pool: asyncpg.Pool, remote_point_slug: str, settings: object
) -> tuple[str, str | None, dict[str, str]]:
    """Retourne (remote_url, ssh_key_path | None, git_env).

    Le PAT n'est JAMAIS mis dans l'URL du remote (persistée en clair dans
    `.git/config`) ni dans l'argv de git. Il est fourni à git via un en-tête
    `http.extraHeader: Authorization: Basic …` passé par l'environnement du
    process (`GIT_CONFIG_COUNT/KEY_0/VALUE_0`, git ≥ 2.31) : non persisté sur
    disque, absent de l'argv. `git_env` contient ces variables (vide pour SSH).
    """
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
        git_host = "github.com"
    elif provider == "gitlab":
        git_host = "gitlab.com"
    else:
        git_host = host
    base_url = f"{git_host}/{repo}.git"

    if point.auth_type == "certificate":
        # SSH — clé privée déchiffrée et écrite dans un fichier temporaire
        if not fernet_key:
            raise RuntimeError("encryption_key non configurée")
        assert point.certificate_slug
        private_key = await rp_svc.get_certificate_private_key(
            pool, point.certificate_slug, fernet_key
        )
        key_path = _REPOS_ROOT / "keys" / f"{point.certificate_slug}.pem"
        await asyncio.to_thread(_write_private_key, key_path, private_key)
        # Syntaxe scp-like : `:` (pas `/`) après le host, sinon git traite la
        # chaîne comme un chemin local et le clone échoue.
        remote_url = f"git@{git_host}:{repo}.git"
        return remote_url, str(key_path), {}

    # PAT : HTTPS, token injecté par en-tête via l'environnement (jamais dans
    # l'URL ni l'argv persistant).
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

    remote_url = f"https://{base_url}"
    token_b64 = base64.b64encode(f"{point.username}:{secret}".encode()).decode()
    git_env = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {token_b64}",
    }
    return remote_url, None, git_env


async def _resolve_dump_auth(
    pool: asyncpg.Pool, remote_point_slug: str, settings: object
) -> tuple[str, int | None, str, str | None, str | None]:
    """Retourne (host, port, username, password_or_None, ssh_key_path_or_None)."""
    from docflow.remote import service as rp_svc

    fernet_key_obj = getattr(settings, "encryption_key", None)
    fernet_key: str | None = fernet_key_obj.reveal() if fernet_key_obj else None
    harpocrate_url: str | None = getattr(settings, "harpocrate_url", None)

    point = await rp_svc.get_point(pool, remote_point_slug)

    if point.auth_type == "certificate":
        if not fernet_key:
            raise RuntimeError("encryption_key non configurée")
        assert point.certificate_slug
        private_key = await rp_svc.get_certificate_private_key(
            pool, point.certificate_slug, fernet_key
        )
        key_path = _REPOS_ROOT / "keys" / f"{point.certificate_slug}.pem"
        await asyncio.to_thread(_write_private_key, key_path, private_key)
        return point.host, point.port, point.username, None, str(key_path)

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

    return point.host, point.port, point.username, secret, None


_DUMPS_ROOT = pathlib.Path("/data/backup-dumps")


async def _run_job(pool: asyncpg.Pool, job: dict[str, Any], settings: object) -> None:
    job_id: uuid.UUID = job["id"]
    log.info("backup_job_start", job_slug=job["slug"], strategy=job["strategy"])

    async with pool.acquire() as conn:
        run_id = await svc.start_run(conn, job_id)

    ssh_key_path: str | None = None
    try:
        if job["strategy"] == "git_sync":
            remote_url, ssh_key_path, git_http_env = await _resolve_git_auth(
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
            host, port, username, password, ssh_key_path = await _resolve_dump_auth(
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
            await asyncio.to_thread(_delete_key_file, ssh_key_path)


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

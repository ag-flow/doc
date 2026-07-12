from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from docflow.backup import runs as runs_svc
from docflow.backup import service as svc
from docflow.backup.schemas import BackupJobCreate, BackupJobUpdate
from docflow.remote import service as rp_svc
from docflow.remote.schemas import RemotePointCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
async def _clean(db_pool: asyncpg.Pool) -> AsyncIterator[None]:
    yield
    await db_pool.execute("DELETE FROM backup_job")
    await db_pool.execute("DELETE FROM remote_point")


@pytest.fixture()
async def remote_point(db_pool: asyncpg.Pool) -> str:
    """Crée un remote point 'ftp-point' et retourne son slug."""
    body = RemotePointCreate(
        slug="ftp-point",
        label="FTP",
        point_type="ftp",
        host="ftp.example.com",
        username="user",
        auth_type="password",
        auth_storage="local",
        auth_secret="s3cr3t",
    )
    await rp_svc.create_point(db_pool, body, _FERNET_KEY)
    return "ftp-point"


def _job_body(slug: str, remote_point_slug: str, **kwargs: object) -> BackupJobCreate:
    return BackupJobCreate(
        slug=slug,
        label=slug,
        strategy="db_dump",
        remote_point_slug=remote_point_slug,
        schedule_every_seconds=3600,
        **kwargs,  # type: ignore[arg-type]
    )


# ── CRUD jobs ─────────────────────────────────────────────────────────────────


async def test_create_job(db_pool: asyncpg.Pool, remote_point: str) -> None:
    job = await svc.create_job(db_pool, _job_body("job-01", remote_point))
    assert job.slug == "job-01"
    assert job.strategy == "db_dump"
    assert job.enabled is True
    assert job.schedule_every_seconds == 3600
    assert job.remote_point_slug == remote_point
    assert job.last_run_at is None
    assert job.last_run_status is None


async def test_create_job_with_cron(db_pool: asyncpg.Pool, remote_point: str) -> None:
    body = BackupJobCreate(
        slug="job-cron",
        label="Cron",
        strategy="db_dump",
        remote_point_slug=remote_point,
        schedule_cron="0 3 * * *",
    )
    job = await svc.create_job(db_pool, body)
    assert job.schedule_cron == "0 3 * * *"
    assert job.schedule_every_seconds is None


async def test_create_job_duplicate_slug(db_pool: asyncpg.Pool, remote_point: str) -> None:
    body = _job_body("job-dup", remote_point)
    await svc.create_job(db_pool, body)
    with pytest.raises(HTTPException) as exc_info:
        await svc.create_job(db_pool, body)
    assert exc_info.value.status_code == 409


async def test_create_job_unknown_remote_point(db_pool: asyncpg.Pool) -> None:
    body = _job_body("job-x", "does-not-exist")
    with pytest.raises(HTTPException) as exc_info:
        await svc.create_job(db_pool, body)
    assert exc_info.value.status_code == 422


async def test_get_job(db_pool: asyncpg.Pool, remote_point: str) -> None:
    await svc.create_job(db_pool, _job_body("job-get", remote_point))
    job = await svc.get_job(db_pool, "job-get")
    assert job.slug == "job-get"


async def test_get_job_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await svc.get_job(db_pool, "missing")
    assert exc_info.value.status_code == 404


async def test_update_job(db_pool: asyncpg.Pool, remote_point: str) -> None:
    await svc.create_job(db_pool, _job_body("job-upd", remote_point))
    update = BackupJobUpdate(
        label="New Label",
        enabled=False,
        remote_point_slug=remote_point,
        schedule_every_seconds=7200,
    )
    job = await svc.update_job(db_pool, "job-upd", update)
    assert job.label == "New Label"
    assert job.enabled is False
    assert job.schedule_every_seconds == 7200


async def test_delete_job(db_pool: asyncpg.Pool, remote_point: str) -> None:
    await svc.create_job(db_pool, _job_body("job-del", remote_point))
    await svc.delete_job(db_pool, "job-del")
    with pytest.raises(HTTPException) as exc_info:
        await svc.get_job(db_pool, "job-del")
    assert exc_info.value.status_code == 404


async def test_delete_job_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await svc.delete_job(db_pool, "missing")
    assert exc_info.value.status_code == 404


async def test_list_jobs(db_pool: asyncpg.Pool, remote_point: str) -> None:
    for slug in ("job-aa", "job-bb"):
        await svc.create_job(db_pool, _job_body(slug, remote_point))
    jobs = await svc.list_jobs(db_pool)
    slugs = {j.slug for j in jobs}
    assert {"job-aa", "job-bb"} <= slugs


# ── Périmètre bloc ────────────────────────────────────────────────────────────


async def test_create_job_with_data_block_scope(
    db_pool: asyncpg.Pool,
    remote_point: str,
    test_workspace: dict[str, object],
    make_block,  # type: ignore[no-untyped-def]
) -> None:
    await type_svc.create_type(db_pool, "test-ws", FunctionalTypeCreate(slug="task", label="Task"))
    await make_block("test-ws", "task", "block-a")
    body = BackupJobCreate(
        slug="job-block",
        label="Job Block",
        strategy="git_sync",
        remote_point_slug=remote_point,
        schedule_every_seconds=3600,
        workspace_slug="test-ws",
        data_block_slug="block-a",
    )
    job = await svc.create_job(db_pool, body)
    assert job.data_block_slug == "block-a"
    assert job.workspace_slug == "test-ws"


async def test_create_job_unknown_data_block(
    db_pool: asyncpg.Pool, remote_point: str, test_workspace: dict[str, object]
) -> None:
    body = BackupJobCreate(
        slug="job-block-x",
        label="Job Block X",
        strategy="git_sync",
        remote_point_slug=remote_point,
        schedule_every_seconds=3600,
        workspace_slug="test-ws",
        data_block_slug="missing-block",
    )
    with pytest.raises(HTTPException) as exc_info:
        await svc.create_job(db_pool, body)
    assert exc_info.value.status_code == 422


# ── Lifecycle run ─────────────────────────────────────────────────────────────


@pytest.fixture()
async def test_job(db_pool: asyncpg.Pool, remote_point: str) -> uuid.UUID:
    job = await svc.create_job(db_pool, _job_body("job-run", remote_point))
    return job.id


async def test_start_run_creates_running_entry(db_pool: asyncpg.Pool, test_job: uuid.UUID) -> None:
    async with db_pool.acquire() as conn:
        run_id = await runs_svc.start_run(conn, test_job)
    assert isinstance(run_id, uuid.UUID)
    job_runs = await runs_svc.list_runs(db_pool, "job-run")
    assert len(job_runs) == 1
    assert job_runs[0].status == "running"
    assert job_runs[0].finished_at is None


async def test_finish_run_success(db_pool: asyncpg.Pool, test_job: uuid.UUID) -> None:
    async with db_pool.acquire() as conn:
        run_id = await runs_svc.start_run(conn, test_job)
    async with db_pool.acquire() as conn:
        await runs_svc.finish_run(
            conn,
            run_id,
            status="success",
            last_change_seq=42,
            files_written=3,
            files_deleted=1,
            commit_sha="abc123.dump",
        )
    job_runs = await runs_svc.list_runs(db_pool, "job-run")
    r = job_runs[0]
    assert r.status == "success"
    assert r.last_change_seq == 42
    assert r.files_written == 3
    assert r.files_deleted == 1
    assert r.commit_sha == "abc123.dump"
    assert r.finished_at is not None
    assert r.error_message is None


async def test_finish_run_error(db_pool: asyncpg.Pool, test_job: uuid.UUID) -> None:
    async with db_pool.acquire() as conn:
        run_id = await runs_svc.start_run(conn, test_job)
    async with db_pool.acquire() as conn:
        await runs_svc.finish_run(conn, run_id, status="error", error_message="pg_dump a échoué")
    job_runs = await runs_svc.list_runs(db_pool, "job-run")
    assert job_runs[0].status == "error"
    assert job_runs[0].error_message == "pg_dump a échoué"
    assert job_runs[0].finished_at is not None


async def test_list_runs_order_desc(db_pool: asyncpg.Pool, test_job: uuid.UUID) -> None:
    """Les runs sont retournés du plus récent au plus ancien."""
    for _ in range(3):
        async with db_pool.acquire() as conn:
            run_id = await runs_svc.start_run(conn, test_job)
        async with db_pool.acquire() as conn:
            await runs_svc.finish_run(conn, run_id, status="success")
    job_runs = await runs_svc.list_runs(db_pool, "job-run")
    assert len(job_runs) == 3
    for i in range(len(job_runs) - 1):
        assert job_runs[i].started_at >= job_runs[i + 1].started_at


async def test_prune_old_runs_keeps_only_retention_count(
    db_pool: asyncpg.Pool, test_job: uuid.UUID
) -> None:
    """Au-delà de RUN_RETENTION runs, les plus anciens sont purgés."""
    for _ in range(runs_svc.RUN_RETENTION + 5):
        async with db_pool.acquire() as conn:
            run_id = await runs_svc.start_run(conn, test_job)
        async with db_pool.acquire() as conn:
            await runs_svc.finish_run(conn, run_id, status="success")
            await runs_svc.prune_old_runs(conn, test_job)

    count: int = await db_pool.fetchval(
        "SELECT count(*) FROM backup_job_run WHERE job_id = $1", test_job
    )
    assert count == runs_svc.RUN_RETENTION


async def test_prune_old_runs_keeps_the_most_recent(
    db_pool: asyncpg.Pool, test_job: uuid.UUID
) -> None:
    """La purge garde les runs les plus récents, pas les plus anciens."""
    run_ids = []
    for _ in range(runs_svc.RUN_RETENTION + 2):
        async with db_pool.acquire() as conn:
            run_id = await runs_svc.start_run(conn, test_job)
            run_ids.append(run_id)
        async with db_pool.acquire() as conn:
            await runs_svc.finish_run(conn, run_id, status="success")
            await runs_svc.prune_old_runs(conn, test_job)

    remaining = {
        r["id"]
        for r in await db_pool.fetch("SELECT id FROM backup_job_run WHERE job_id = $1", test_job)
    }
    assert remaining == set(run_ids[-runs_svc.RUN_RETENTION :])


async def test_list_runs_job_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await runs_svc.list_runs(db_pool, "missing-job")
    assert exc_info.value.status_code == 404


async def test_job_last_run_status_reflected(db_pool: asyncpg.Pool, test_job: uuid.UUID) -> None:
    """get_job reflète le statut de la dernière exécution."""
    async with db_pool.acquire() as conn:
        run_id = await runs_svc.start_run(conn, test_job)
    async with db_pool.acquire() as conn:
        await runs_svc.finish_run(conn, run_id, status="success", files_written=1)
    job = await svc.get_job(db_pool, "job-run")
    assert job.last_run_status == "success"
    assert job.last_run_at is not None


# ── Déclenchement manuel ──────────────────────────────────────────────────────


async def test_trigger_run_now_starts_background_run(
    db_pool: asyncpg.Pool, remote_point: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    await svc.create_job(db_pool, _job_body("job-trigger", remote_point))
    calls: dict[str, object] = {}

    async def _fake_run_job(
        pool: asyncpg.Pool,
        job: dict[str, object],
        settings: object,
        *,
        run_id: uuid.UUID | None = None,
    ) -> None:
        calls["run_id"] = run_id
        calls["job_slug"] = job["slug"]

    monkeypatch.setattr("docflow.backup.worker.run_job", _fake_run_job)
    run = await runs_svc.trigger_run_now(db_pool, object(), "job-trigger")
    assert run.status == "running"
    await asyncio.sleep(0)  # laisse la tâche de fond s'exécuter
    assert calls["job_slug"] == "job-trigger"
    assert calls["run_id"] == run.id


async def test_trigger_run_now_job_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await runs_svc.trigger_run_now(db_pool, object(), "missing")
    assert exc_info.value.status_code == 404


async def test_trigger_run_now_conflict_if_already_running(
    db_pool: asyncpg.Pool, remote_point: str
) -> None:
    job = await svc.create_job(db_pool, _job_body("job-busy", remote_point))
    async with db_pool.acquire() as conn:
        await runs_svc.start_run(conn, job.id)

    with pytest.raises(HTTPException) as exc_info:
        await runs_svc.trigger_run_now(db_pool, object(), "job-busy")
    assert exc_info.value.status_code == 409


# ── Validation Pydantic ───────────────────────────────────────────────────────


def test_job_data_block_slug_requires_workspace_slug() -> None:
    with pytest.raises(ValueError, match="data_block_slug requiert workspace_slug"):
        BackupJobCreate(
            slug="bad-job",
            label="Bad",
            strategy="git_sync",
            remote_point_slug="pt",
            schedule_every_seconds=3600,
            data_block_slug="block-a",
        )


def test_job_requires_at_least_one_schedule() -> None:
    with pytest.raises(ValueError, match="exactement un"):
        BackupJobCreate(
            slug="bad-job",
            label="Bad",
            strategy="db_dump",
            remote_point_slug="pt",
        )


def test_job_rejects_both_schedules() -> None:
    with pytest.raises(ValueError, match="exactement un"):
        BackupJobCreate(
            slug="bad-job",
            label="Bad",
            strategy="db_dump",
            remote_point_slug="pt",
            schedule_cron="0 * * * *",
            schedule_every_seconds=3600,
        )

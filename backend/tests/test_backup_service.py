from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from docflow.backup import service as svc
from docflow.backup.schemas import BackupJobCreate, BackupJobUpdate
from docflow.remote import service as rp_svc
from docflow.remote.schemas import RemotePointCreate

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


# ── Lifecycle run ─────────────────────────────────────────────────────────────


@pytest.fixture()
async def test_job(db_pool: asyncpg.Pool, remote_point: str) -> uuid.UUID:
    job = await svc.create_job(db_pool, _job_body("job-run", remote_point))
    return job.id


async def test_start_run_creates_running_entry(db_pool: asyncpg.Pool, test_job: uuid.UUID) -> None:
    async with db_pool.acquire() as conn:
        run_id = await svc.start_run(conn, test_job)
    assert isinstance(run_id, uuid.UUID)
    runs = await svc.list_runs(db_pool, "job-run")
    assert len(runs) == 1
    assert runs[0].status == "running"
    assert runs[0].finished_at is None


async def test_finish_run_success(db_pool: asyncpg.Pool, test_job: uuid.UUID) -> None:
    async with db_pool.acquire() as conn:
        run_id = await svc.start_run(conn, test_job)
    async with db_pool.acquire() as conn:
        await svc.finish_run(
            conn,
            run_id,
            status="success",
            last_change_seq=42,
            files_written=3,
            files_deleted=1,
            commit_sha="abc123.dump",
        )
    runs = await svc.list_runs(db_pool, "job-run")
    r = runs[0]
    assert r.status == "success"
    assert r.last_change_seq == 42
    assert r.files_written == 3
    assert r.files_deleted == 1
    assert r.commit_sha == "abc123.dump"
    assert r.finished_at is not None
    assert r.error_message is None


async def test_finish_run_error(db_pool: asyncpg.Pool, test_job: uuid.UUID) -> None:
    async with db_pool.acquire() as conn:
        run_id = await svc.start_run(conn, test_job)
    async with db_pool.acquire() as conn:
        await svc.finish_run(conn, run_id, status="error", error_message="pg_dump a échoué")
    runs = await svc.list_runs(db_pool, "job-run")
    assert runs[0].status == "error"
    assert runs[0].error_message == "pg_dump a échoué"
    assert runs[0].finished_at is not None


async def test_list_runs_order_desc(db_pool: asyncpg.Pool, test_job: uuid.UUID) -> None:
    """Les runs sont retournés du plus récent au plus ancien."""
    for _ in range(3):
        async with db_pool.acquire() as conn:
            run_id = await svc.start_run(conn, test_job)
        async with db_pool.acquire() as conn:
            await svc.finish_run(conn, run_id, status="success")
    runs = await svc.list_runs(db_pool, "job-run")
    assert len(runs) == 3
    for i in range(len(runs) - 1):
        assert runs[i].started_at >= runs[i + 1].started_at


async def test_list_runs_job_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await svc.list_runs(db_pool, "missing-job")
    assert exc_info.value.status_code == 404


async def test_job_last_run_status_reflected(db_pool: asyncpg.Pool, test_job: uuid.UUID) -> None:
    """get_job reflète le statut de la dernière exécution."""
    async with db_pool.acquire() as conn:
        run_id = await svc.start_run(conn, test_job)
    async with db_pool.acquire() as conn:
        await svc.finish_run(conn, run_id, status="success", files_written=1)
    job = await svc.get_job(db_pool, "job-run")
    assert job.last_run_status == "success"
    assert job.last_run_at is not None


# ── Validation Pydantic ───────────────────────────────────────────────────────


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

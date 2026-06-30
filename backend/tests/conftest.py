from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest

from docflow.db.apply import apply

_TEST_SCHEMA = "docflow_test"


def _base_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB integration tests")
    return url


def _schema_url(base: str) -> str:
    """Return base DSN with search_path pinned to the test schema.

    public est conservé en second pour que les classes d'opérateurs des
    extensions (pg_trgm → gin_trgm_ops) restent accessibles.
    """
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}options=-csearch_path%3D{_TEST_SCHEMA}%2Cpublic"


@pytest.fixture(scope="session")
def test_schema_url() -> Iterator[str]:
    """Create the test schema once for the session; tear it down afterwards.

    Uses a dedicated event loop (not pytest-asyncio's) to avoid conflicts.
    """
    base = _base_db_url()

    async def _setup() -> None:
        conn: asyncpg.Connection = await asyncpg.connect(base)
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {_TEST_SCHEMA} CASCADE")
            await conn.execute(f"CREATE SCHEMA {_TEST_SCHEMA}")
        finally:
            await conn.close()

    async def _teardown() -> None:
        conn = await asyncpg.connect(base)
        try:
            await conn.execute(f"DROP SCHEMA IF EXISTS {_TEST_SCHEMA} CASCADE")
        finally:
            await conn.close()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_setup())
    finally:
        loop.close()

    yield _schema_url(base)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_teardown())
    finally:
        loop.close()


@pytest.fixture(scope="session")
def apply_migrations(test_schema_url: str) -> None:
    """Run migrations once at session level so all tables exist for every test."""

    async def _do() -> None:
        pool: asyncpg.Pool = await asyncpg.create_pool(  # type: ignore[assignment]
            dsn=test_schema_url, min_size=1, max_size=1
        )
        try:
            await apply(pool)
        finally:
            await pool.close()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_do())
    finally:
        loop.close()


@pytest.fixture()
async def db_pool(test_schema_url: str, apply_migrations: None) -> AsyncIterator[asyncpg.Pool]:
    """Function-scoped pool wired to the test schema.

    Tables created by apply() land in the test schema and are dropped
    at session teardown via test_schema_url.
    """
    pool: asyncpg.Pool = await asyncpg.create_pool(  # type: ignore[assignment]
        dsn=test_schema_url,
        min_size=1,
        max_size=3,
    )
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture()
def clean_admin_users(test_schema_url: str, apply_migrations: None) -> Iterator[None]:
    """Truncate app_user (and cascaded tables) before the test that requests this fixture."""

    async def _truncate() -> None:
        conn: asyncpg.Connection = await asyncpg.connect(test_schema_url)
        try:
            await conn.execute("TRUNCATE app_user CASCADE")
        finally:
            await conn.close()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_truncate())
    finally:
        loop.close()
    yield


@pytest.fixture()
async def test_workspace(db_pool: asyncpg.Pool) -> AsyncIterator[dict[str, object]]:
    """Create a workspace for M3/M4+ tests; delete it (+ cascade) after the test."""
    row = await db_pool.fetchrow(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) "
        "RETURNING workspace_technical_key, slug, label",
        "test-ws", "Test Workspace",
    )
    assert row is not None
    yield dict(row)
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "test-ws")


@pytest.fixture()
async def test_block(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> AsyncIterator[dict[str, object]]:
    """Crée un type racine 'root-type' et un bloc 'test-block' dans le workspace test.

    Cède un dict {id, slug, type_id, type_slug}.
    Le cleanup est pris en charge par la cascade du workspace (DELETE workspace).
    """
    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]

    # Créer le type fonctionnel racine
    type_row = await db_pool.fetchrow(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ($1, $2, $3) RETURNING id, slug",
        "root-type", "Root Type", wk,
    )
    assert type_row is not None
    type_id: uuid.UUID = type_row["id"]
    type_slug: str = type_row["slug"]

    # Créer le bloc
    block_row = await db_pool.fetchrow(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) RETURNING id, slug",
        "test-block", "Test Block", type_id, wk,
    )
    assert block_row is not None

    yield {
        "id": block_row["id"],
        "slug": block_row["slug"],
        "type_id": type_id,
        "type_slug": type_slug,
    }

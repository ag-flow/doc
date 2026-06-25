from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest

_TEST_SCHEMA = "docflow_test"


def _base_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB integration tests")
    return url


def _schema_url(base: str) -> str:
    """Return base DSN with search_path pinned to the test schema."""
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}options=-csearch_path%3D{_TEST_SCHEMA}"


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


@pytest.fixture()
async def db_pool(test_schema_url: str) -> AsyncIterator[asyncpg.Pool]:
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

from __future__ import annotations

import asyncpg

from docflow.db.apply import apply


async def test_apply_on_empty_db(db_pool: asyncpg.Pool) -> None:
    """apply() on a fresh schema creates schema_migrations and runs 0001_init."""
    await apply(db_pool)

    version = await db_pool.fetchval(
        "SELECT version FROM schema_migrations WHERE version = $1",
        "0001_init",
    )
    assert version == "0001_init"


async def test_apply_creates_all_tables(db_pool: asyncpg.Pool) -> None:
    """After apply(), all tables from 0001_init.sql must exist."""
    await apply(db_pool)

    expected = {
        "admin_user",
        "oidc_config",
        "workspace",
        "functional_type",
        "data_block",
        "document",
        "properties_defs",
        "properties_constraints",
        "properties_allowed_values",
        "properties_values",
        "schema_migrations",
    }
    rows = await db_pool.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_type = 'BASE TABLE'
        """
    )
    existing = {row["table_name"] for row in rows}
    assert expected <= existing


async def test_apply_idempotent(db_pool: asyncpg.Pool) -> None:
    """Calling apply() twice must not re-apply any migration."""
    await apply(db_pool)

    count_before = await db_pool.fetchval("SELECT COUNT(*) FROM schema_migrations")

    await apply(db_pool)

    count_after = await db_pool.fetchval("SELECT COUNT(*) FROM schema_migrations")
    assert count_after == count_before


async def test_apply_records_version(db_pool: asyncpg.Pool) -> None:
    """schema_migrations must record applied_at as a timestamptz."""
    await apply(db_pool)

    row = await db_pool.fetchrow(
        "SELECT version, applied_at FROM schema_migrations WHERE version = $1",
        "0001_init",
    )
    assert row is not None
    assert row["version"] == "0001_init"
    assert row["applied_at"] is not None

from __future__ import annotations

from typing import Any

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def open_pool(dsn: str, **kwargs: Any) -> asyncpg.Pool:
    """Create and return an asyncpg connection pool.

    min_size=0 so the pool is created even when the DB is temporarily unreachable
    (health endpoint then returns 503 instead of failing at startup).
    """
    pool: asyncpg.Pool = await asyncpg.create_pool(dsn=dsn, min_size=0, max_size=10, **kwargs)
    log.info("db_pool_opened")
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    await pool.close()
    log.info("db_pool_closed")

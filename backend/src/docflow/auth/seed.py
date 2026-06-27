from __future__ import annotations

import asyncpg
import structlog

from docflow.auth.password import hash_password
from docflow.config.settings import Settings

log = structlog.get_logger(__name__)

_COUNT_ADMINS = "SELECT COUNT(*) FROM admin_user"
_INSERT_ADMIN = """
INSERT INTO admin_user (email, label, password_hash, is_superadmin, disabled)
VALUES ($1, $2, $3, true, false)
"""


async def seed_bootstrap_admin(pool: asyncpg.Pool, settings: Settings) -> None:
    """Insert the bootstrap admin if admin_user is empty. Idempotent."""
    async with pool.acquire() as conn:
        count: int = await conn.fetchval(_COUNT_ADMINS)
        if count > 0:
            log.debug("bootstrap_admin_skipped", existing_count=count)
            return

        hashed = hash_password(settings.admin_password.reveal())
        await conn.execute(_INSERT_ADMIN, settings.admin_email, settings.admin_email, hashed)
        log.info("bootstrap_admin_created", email=settings.admin_email)

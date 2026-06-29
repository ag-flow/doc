from __future__ import annotations

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.auth.password import hash_password
from docflow.schemas.admin_user import AdminUserOut
from docflow.schemas.setup import InitAdminRequest

log = structlog.get_logger(__name__)

_COUNT = "SELECT COUNT(*) FROM app_user"

_INSERT = """
INSERT INTO app_user (username, email, label, password_hash, is_admin, validated, disabled, source)
VALUES ($1, $2, $3, $4, true, true, false, 'local')
RETURNING id, email, label, username, source, is_admin, validated, disabled,
          (password_hash IS NOT NULL) AS has_local_password,
          created_at, updated_at
"""


async def user_count(conn: asyncpg.Connection) -> int:
    result: int = await conn.fetchval(_COUNT)
    return result


async def init_admin(pool: asyncpg.Pool, body: InitAdminRequest) -> AdminUserOut:
    hashed = hash_password(body.password)
    async with pool.acquire() as conn:
        async with conn.transaction():
            count: int = await conn.fetchval(_COUNT)
            if count > 0:
                raise HTTPException(status_code=409, detail="SetupAlreadyDone")
            try:
                row = await conn.fetchrow(_INSERT, body.username, body.email, body.username, hashed)
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(status_code=409, detail="SetupAlreadyDone") from exc

    log.info("setup_admin_created", email=body.email, username=body.username)
    assert row is not None
    return AdminUserOut(
        id=row["id"],
        email=row["email"],
        label=row["label"],
        username=row["username"],
        source=row["source"],
        is_admin=row["is_admin"],
        validated=row["validated"],
        disabled=row["disabled"],
        has_local_password=row["has_local_password"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

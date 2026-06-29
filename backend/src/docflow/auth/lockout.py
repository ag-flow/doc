from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

_COUNT_LOCAL_ADMINS = """
SELECT COUNT(*) FROM app_user
WHERE password_hash IS NOT NULL
  AND disabled = false
  AND is_admin = true
  AND id != $1
"""


async def assert_not_last_local_admin(
    conn: asyncpg.Connection,
    exclude_id: uuid.UUID,
) -> None:
    """Raise 422 if removing/disabling exclude_id would leave no connectable local admin.

    Must be called inside the same transaction as the modifying statement.
    """
    remaining: int = await conn.fetchval(_COUNT_LOCAL_ADMINS, exclude_id)
    if remaining == 0:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "last_local_admin",
                "message": (
                    "Impossible : cet admin est le dernier compte local connectable "
                    "par mot de passe. Créez un autre admin local avant de modifier celui-ci."
                ),
            },
        )

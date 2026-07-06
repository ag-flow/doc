from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

_COUNT_LOCAL_ADMINS = """
SELECT COUNT(*) FROM app_user
WHERE password_hash IS NOT NULL
  AND disabled = false
  AND is_admin = true
  AND validated = true
  AND id != $1
"""

_IS_CONNECTABLE_LOCAL_ADMIN = """
SELECT EXISTS(
    SELECT 1 FROM app_user
    WHERE id = $1
      AND password_hash IS NOT NULL
      AND disabled = false
      AND is_admin = true
      AND validated = true
)
"""


async def assert_not_last_local_admin(
    conn: asyncpg.Connection,
    exclude_id: uuid.UUID,
) -> None:
    """Raise 422 if removing/disabling exclude_id would leave no connectable local admin.

    Si exclude_id n'est pas lui-même un admin local connectable, l'opération ne peut
    pas réduire le pool d'admins connectables : le garde est no-op (sinon, une base
    sans admin local — p. ex. tout-OIDC — bloquerait toute mutation d'utilisateur).

    Must be called inside the same transaction as the modifying statement.
    """
    target_is_admin: bool = await conn.fetchval(_IS_CONNECTABLE_LOCAL_ADMIN, exclude_id)
    if not target_is_admin:
        return
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

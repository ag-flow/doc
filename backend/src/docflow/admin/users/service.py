from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.auth.lockout import assert_not_last_local_admin
from docflow.auth.password import hash_password
from docflow.schemas.admin_user import AdminUserCreate, AdminUserOut, AdminUserUpdate

_SELECT_ALL = """
SELECT id, email, label, is_superadmin, disabled,
       (password_hash IS NOT NULL) AS has_local_password,
       created_at, updated_at
FROM admin_user ORDER BY created_at
"""

_SELECT_ONE = """
SELECT id, email, label, is_superadmin, disabled,
       (password_hash IS NOT NULL) AS has_local_password,
       created_at, updated_at
FROM admin_user WHERE id = $1
"""

_INSERT = """
INSERT INTO admin_user (email, label, password_hash, is_superadmin, disabled)
VALUES ($1, $2, $3, $4, false)
RETURNING id, email, label, is_superadmin, disabled,
          (password_hash IS NOT NULL) AS has_local_password,
          created_at, updated_at
"""

_CHECK_EMAIL_UNIQUE = "SELECT id FROM admin_user WHERE email = $1 AND id != $2"

# Ensemble fini des colonnes modifiables — protège le UPDATE dynamique.
_UPDATABLE_COLUMNS = frozenset({"email", "label", "is_superadmin", "disabled"})


def _row_to_out(row: asyncpg.Record) -> AdminUserOut:
    return AdminUserOut(
        id=row["id"],
        email=row["email"],
        label=row["label"],
        is_superadmin=row["is_superadmin"],
        disabled=row["disabled"],
        has_local_password=row["has_local_password"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def list_users(pool: asyncpg.Pool) -> list[AdminUserOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SELECT_ALL)
    return [_row_to_out(r) for r in rows]


async def get_user(pool: asyncpg.Pool, user_id: uuid.UUID) -> AdminUserOut:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT_ONE, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="admin introuvable")
    return _row_to_out(row)


async def create_user(pool: asyncpg.Pool, data: AdminUserCreate) -> AdminUserOut:
    hashed = hash_password(data.password)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                _INSERT, data.email, data.label, hashed, data.is_superadmin
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(status_code=409, detail="email déjà utilisé") from exc
    assert row is not None
    return _row_to_out(row)


async def update_user(
    pool: asyncpg.Pool, user_id: uuid.UUID, data: AdminUserUpdate
) -> AdminUserOut:
    updates: dict[str, object] = {
        k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None
    }
    if not updates:
        return await get_user(pool, user_id)

    for k in updates:
        if k not in _UPDATABLE_COLUMNS:
            raise ValueError(f"colonne non autorisée : {k}")

    async with pool.acquire() as conn:
        # Vérification anti-lock-out si on désactive
        async with conn.transaction():
            if updates.get("disabled") is True:
                await assert_not_last_local_admin(conn, user_id)

            if "email" in updates:
                conflict = await conn.fetchval(_CHECK_EMAIL_UNIQUE, updates["email"], user_id)
                if conflict:
                    raise HTTPException(status_code=409, detail="email déjà utilisé")

            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
            vals = list(updates.values())
            sql = f"""
                UPDATE admin_user
                SET {cols}, updated_at = now()
                WHERE id = $1
                RETURNING id, email, label, is_superadmin, disabled,
                          (password_hash IS NOT NULL) AS has_local_password,
                          created_at, updated_at
            """
            row = await conn.fetchrow(sql, user_id, *vals)

    if row is None:
        raise HTTPException(status_code=404, detail="admin introuvable")
    return _row_to_out(row)


async def delete_user(pool: asyncpg.Pool, user_id: uuid.UUID) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT password_hash, disabled FROM admin_user WHERE id = $1",
                user_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="admin introuvable")
            # Anti-lock-out : vérifier seulement si c'est un admin local actif
            if row["password_hash"] is not None and not row["disabled"]:
                await assert_not_last_local_admin(conn, user_id)
            await conn.execute("DELETE FROM admin_user WHERE id = $1", user_id)


async def set_password(
    pool: asyncpg.Pool, user_id: uuid.UUID, new_password: str
) -> AdminUserOut:
    hashed = hash_password(new_password)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE admin_user SET password_hash = $2, updated_at = now()
            WHERE id = $1
            RETURNING id, email, label, is_superadmin, disabled,
                      (password_hash IS NOT NULL) AS has_local_password,
                      created_at, updated_at
            """,
            user_id,
            hashed,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="admin introuvable")
    return _row_to_out(row)

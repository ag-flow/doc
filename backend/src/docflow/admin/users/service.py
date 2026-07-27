from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.auth.lockout import assert_not_last_local_admin
from docflow.auth.password import hash_password
from docflow.schemas.admin_user import AdminUserCreate, AdminUserOut, AdminUserUpdate

_COLS = """
    id, email, label, username, source, is_admin, validated, disabled,
    (password_hash IS NOT NULL) AS has_local_password,
    created_at, updated_at, last_login_at,
    ((SELECT count(*) FROM workspace_member m WHERE m.user_id = app_user.id)
     + (SELECT count(*) FROM workspace w WHERE w.owner_id = app_user.id
         AND NOT EXISTS (SELECT 1 FROM workspace_member m2
                          WHERE m2.workspace_technical_key = w.workspace_technical_key
                            AND m2.user_id = app_user.id))) AS workspaces_count
"""

_SELECT_ALL = f"SELECT {_COLS} FROM app_user ORDER BY created_at"
_SELECT_ONE = f"SELECT {_COLS} FROM app_user WHERE id = $1"

_INSERT = f"""
INSERT INTO app_user (email, label, password_hash, is_admin, validated, disabled, source)
VALUES ($1, $2, $3, $4, true, false, 'local')
RETURNING {_COLS}
"""

_CHECK_EMAIL_UNIQUE = "SELECT id FROM app_user WHERE email = $1 AND id != $2"

_UPDATABLE_COLUMNS = frozenset({"email", "label", "is_admin", "validated", "disabled"})


def _row_to_out(row: asyncpg.Record) -> AdminUserOut:
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
        last_login_at=row["last_login_at"] if "last_login_at" in row.keys() else None,
        workspaces_count=row["workspaces_count"] if "workspaces_count" in row.keys() else 0,
    )


async def list_users(pool: asyncpg.Pool) -> list[AdminUserOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SELECT_ALL)
    return [_row_to_out(r) for r in rows]


async def get_user(pool: asyncpg.Pool, user_id: uuid.UUID) -> AdminUserOut:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT_ONE, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="utilisateur introuvable")
    return _row_to_out(row)


async def create_user(pool: asyncpg.Pool, data: AdminUserCreate) -> AdminUserOut:
    hashed = hash_password(data.password)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(_INSERT, data.email, data.label, hashed, data.is_admin)
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
        async with conn.transaction():
            # Toute mutation retirant la qualité d'admin local connectable (désactivation,
            # démotion is_admin OU dévalidation) doit passer le garde anti-lock-out.
            # Cf. AUTH-03 et AUTH-04 (même invariant : validated compte désormais).
            if (
                updates.get("disabled") is True
                or updates.get("is_admin") is False
                or updates.get("validated") is False
            ):
                await assert_not_last_local_admin(conn, user_id)

            if "email" in updates:
                conflict = await conn.fetchval(_CHECK_EMAIL_UNIQUE, updates["email"], user_id)
                if conflict:
                    raise HTTPException(status_code=409, detail="email déjà utilisé")

            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
            vals = list(updates.values())
            sql = f"""
                UPDATE app_user
                SET {cols}, updated_at = now()
                WHERE id = $1
                RETURNING {_COLS}
            """
            row = await conn.fetchrow(sql, user_id, *vals)

    if row is None:
        raise HTTPException(status_code=404, detail="utilisateur introuvable")
    return _row_to_out(row)


async def validate_user(pool: asyncpg.Pool, user_id: uuid.UUID, *, validated: bool) -> AdminUserOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Dévalider un compte le rend non connectable (403 PendingValidation) : c'est
            # un chemin de lock-out qui doit passer le garde anti-lock-out. Cf. AUTH-04.
            if not validated:
                await assert_not_last_local_admin(conn, user_id)
            row = await conn.fetchrow(
                f"UPDATE app_user SET validated = $2, updated_at = now()"
                f" WHERE id = $1 RETURNING {_COLS}",
                user_id,
                validated,
            )
    if row is None:
        raise HTTPException(status_code=404, detail="utilisateur introuvable")
    return _row_to_out(row)


async def delete_user(pool: asyncpg.Pool, user_id: uuid.UUID) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM app_user WHERE id = $1)", user_id
            )
            if not exists:
                raise HTTPException(status_code=404, detail="utilisateur introuvable")
            # Le garde est no-op si la cible n'est pas un admin local connectable.
            await assert_not_last_local_admin(conn, user_id)
            await conn.execute("DELETE FROM app_user WHERE id = $1", user_id)


async def set_password(pool: asyncpg.Pool, user_id: uuid.UUID, new_password: str) -> AdminUserOut:
    hashed = hash_password(new_password)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE app_user SET password_hash = $2, updated_at = now()
            WHERE id = $1
            RETURNING {_COLS}
            """,
            user_id,
            hashed,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="utilisateur introuvable")
    return _row_to_out(row)

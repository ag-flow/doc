from __future__ import annotations

import hashlib
import secrets
import uuid

import asyncpg
from fastapi import HTTPException

from docflow.apikeys.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ApiProfileCreate,
    ApiProfileDetail,
    ApiProfileOut,
    ApiProfileScopeIn,
    ApiProfileScopeOut,
)
from docflow.schemas.auth import AuthUser


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _generate_raw_key() -> str:
    return "dfk_" + secrets.token_urlsafe(32)


async def list_profiles(pool: asyncpg.Pool, owner_id: uuid.UUID) -> list[ApiProfileOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.id, p.name, p.description, p.is_admin, p.created_at, p.updated_at,
                   COUNT(DISTINCT s.id)::int AS scope_count,
                   COUNT(DISTINCT k.id) FILTER (WHERE k.revoked_at IS NULL)::int AS key_count
            FROM api_profile p
            LEFT JOIN api_profile_scope s ON s.profile_id = p.id
            LEFT JOIN api_key k ON k.profile_id = p.id
            WHERE p.owner_id = $1
            GROUP BY p.id
            ORDER BY p.created_at
            """,
            owner_id,
        )
    return [ApiProfileOut(**dict(r)) for r in rows]


async def create_profile(
    pool: asyncpg.Pool, owner_id: uuid.UUID, body: ApiProfileCreate
) -> ApiProfileOut:
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO api_profile (owner_id, name, description, is_admin)
                VALUES ($1, $2, $3, $4)
                RETURNING id, name, description, is_admin, created_at, updated_at
                """,
                owner_id,
                body.name,
                body.description,
                body.is_admin,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(status_code=409, detail="nom de profil déjà utilisé") from exc
    assert row is not None
    return ApiProfileOut(**dict(row), scope_count=0, key_count=0)


async def get_profile(
    pool: asyncpg.Pool, owner_id: uuid.UUID, profile_id: uuid.UUID
) -> ApiProfileDetail:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.id, p.name, p.description, p.is_admin, p.created_at, p.updated_at,
                   COUNT(DISTINCT s.id)::int AS scope_count,
                   COUNT(DISTINCT k.id) FILTER (WHERE k.revoked_at IS NULL)::int AS key_count
            FROM api_profile p
            LEFT JOIN api_profile_scope s ON s.profile_id = p.id
            LEFT JOIN api_key k ON k.profile_id = p.id
            WHERE p.id = $1 AND p.owner_id = $2
            GROUP BY p.id
            """,
            profile_id,
            owner_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="profil introuvable")
        scope_rows = await conn.fetch(
            """
            SELECT id, workspace_slug, block_slug, read_only
            FROM api_profile_scope
            WHERE profile_id = $1
            ORDER BY workspace_slug, block_slug NULLS FIRST
            """,
            profile_id,
        )
    scopes = [ApiProfileScopeOut(**dict(s)) for s in scope_rows]
    return ApiProfileDetail(**dict(row), scopes=scopes)


async def set_scopes(
    pool: asyncpg.Pool,
    owner_id: uuid.UUID,
    profile_id: uuid.UUID,
    scopes: list[ApiProfileScopeIn],
) -> list[ApiProfileScopeOut]:
    seen: set[tuple[str, str | None]] = set()
    for s in scopes:
        key = (s.workspace_slug, s.block_slug)
        if key in seen:
            raise HTTPException(status_code=422, detail="scopes dupliqués dans la liste")
        seen.add(key)

    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM api_profile WHERE id = $1 AND owner_id = $2",
            profile_id,
            owner_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="profil introuvable")
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM api_profile_scope WHERE profile_id = $1", profile_id
            )
            rows = []
            for s in scopes:
                r = await conn.fetchrow(
                    """
                    INSERT INTO api_profile_scope
                        (profile_id, workspace_slug, block_slug, read_only)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, workspace_slug, block_slug, read_only
                    """,
                    profile_id,
                    s.workspace_slug,
                    s.block_slug,
                    s.read_only,
                )
                rows.append(r)
            await conn.execute(
                "UPDATE api_profile SET updated_at = now() WHERE id = $1", profile_id
            )
    return [ApiProfileScopeOut(**dict(r)) for r in rows]


async def delete_profile(
    pool: asyncpg.Pool, owner_id: uuid.UUID, profile_id: uuid.UUID
) -> None:
    async with pool.acquire() as conn:
        deleted = await conn.execute(
            "DELETE FROM api_profile WHERE id = $1 AND owner_id = $2",
            profile_id,
            owner_id,
        )
    if deleted == "DELETE 0":
        raise HTTPException(status_code=404, detail="profil introuvable")


async def list_keys(pool: asyncpg.Pool, owner_id: uuid.UUID) -> list[ApiKeyOut]:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM api_key
            WHERE owner_id = $1
              AND revoked_at IS NOT NULL
              AND revoked_at < now() - interval '24 hours'
            """,
            owner_id,
        )
        rows = await conn.fetch(
            """
            SELECT k.id, k.profile_id, p.name AS profile_name, k.label,
                   k.key_prefix, k.created_at, k.last_used_at,
                   (k.revoked_at IS NOT NULL) AS revoked
            FROM api_key k
            JOIN api_profile p ON p.id = k.profile_id
            WHERE k.owner_id = $1
            ORDER BY k.created_at DESC
            """,
            owner_id,
        )
    return [ApiKeyOut(**dict(r)) for r in rows]


async def generate_key(
    pool: asyncpg.Pool, owner_id: uuid.UUID, body: ApiKeyCreate
) -> ApiKeyCreated:
    async with pool.acquire() as conn:
        profile = await conn.fetchrow(
            "SELECT id, name FROM api_profile WHERE id = $1 AND owner_id = $2",
            body.profile_id,
            owner_id,
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="profil introuvable")

        raw = _generate_raw_key()
        prefix = raw[:12]
        key_hash = _hash_key(raw)

        row = await conn.fetchrow(
            """
            INSERT INTO api_key (profile_id, owner_id, label, key_prefix, key_hash)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, profile_id, label, key_prefix, created_at, last_used_at,
                      (revoked_at IS NOT NULL) AS revoked
            """,
            body.profile_id,
            owner_id,
            body.label,
            prefix,
            key_hash,
        )
    assert row is not None
    return ApiKeyCreated(**dict(row), profile_name=profile["name"], key=raw)


async def revoke_key(
    pool: asyncpg.Pool, owner_id: uuid.UUID, key_id: uuid.UUID
) -> None:
    async with pool.acquire() as conn:
        updated = await conn.execute(
            """
            UPDATE api_key SET revoked_at = now()
            WHERE id = $1 AND owner_id = $2 AND revoked_at IS NULL
            """,
            key_id,
            owner_id,
        )
    if updated == "UPDATE 0":
        raise HTTPException(status_code=404, detail="clé introuvable ou déjà révoquée")


async def resolve_api_key(
    pool: asyncpg.Pool, raw: str
) -> tuple[AuthUser, list[ApiProfileScopeOut], bool]:
    """Retourne (AuthUser, scopes, profile_is_admin).

    profile_is_admin=True : la clé appartient à un profil admin — aucune restriction de scope.
    """
    key_hash = _hash_key(raw)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT k.id AS key_id, k.owner_id,
                   u.email, u.label, u.is_admin AS user_is_admin,
                   u.validated, u.disabled,
                   p.is_admin AS profile_is_admin
            FROM api_key k
            JOIN app_user u ON u.id = k.owner_id
            JOIN api_profile p ON p.id = k.profile_id
            WHERE k.key_hash = $1 AND k.revoked_at IS NULL
            """,
            key_hash,
        )
        if row is None:
            raise HTTPException(status_code=401, detail="clé API invalide ou révoquée")
        if row["disabled"] or not row["validated"]:
            raise HTTPException(status_code=401, detail="compte désactivé ou non validé")
        scope_rows = await conn.fetch(
            """
            SELECT s.id, s.workspace_slug, s.block_slug, s.read_only
            FROM api_profile_scope s
            JOIN api_key k ON k.profile_id = s.profile_id
            WHERE k.key_hash = $1 AND k.revoked_at IS NULL
            ORDER BY s.workspace_slug, s.block_slug NULLS FIRST
            """,
            key_hash,
        )
        await conn.execute(
            "UPDATE api_key SET last_used_at = now() WHERE key_hash = $1", key_hash
        )
    user = AuthUser(
        id=row["owner_id"],
        email=row["email"],
        label=row["label"],
        is_admin=row["user_is_admin"],
        validated=row["validated"],
        disabled=row["disabled"],
    )
    scopes = [ApiProfileScopeOut(**dict(s)) for s in scope_rows]
    return user, scopes, bool(row["profile_is_admin"])

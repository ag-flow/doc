from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.schemas.auth import AuthUser

_VALID_ROLES = ("owner", "member")


async def _resolve_ws(conn: asyncpg.Connection, ws_slug: str) -> tuple[uuid.UUID, uuid.UUID | None]:
    row = await conn.fetchrow(
        "SELECT workspace_technical_key, owner_id FROM workspace WHERE slug = $1",
        ws_slug,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"workspace '{ws_slug}' introuvable")
    return row["workspace_technical_key"], row["owner_id"]


def _require_manager(actor: AuthUser, owner_id: uuid.UUID | None) -> None:
    """Seuls l'owner du workspace ou un superadmin gèrent les membres."""
    if actor.is_admin:
        return
    if owner_id is not None and owner_id == actor.id:
        return
    raise HTTPException(
        status_code=403,
        detail="gestion des membres réservée à l'owner du workspace ou à un superadmin",
    )


async def list_members(pool: asyncpg.Pool, ws_slug: str) -> dict[str, object]:
    """Membres du workspace (email, role) plus l'email de l'owner."""
    async with pool.acquire() as conn:
        ws_key, owner_id = await _resolve_ws(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT u.email, m.role
            FROM workspace_member m
            JOIN app_user u ON u.id = m.user_id
            WHERE m.workspace_technical_key = $1
            ORDER BY u.email
            """,
            ws_key,
        )
        owner_email = (
            await conn.fetchval("SELECT email FROM app_user WHERE id = $1", owner_id)
            if owner_id is not None
            else None
        )
    return {
        "workspace_slug": ws_slug,
        "owner_email": owner_email,
        "members": [{"email": r["email"], "role": r["role"]} for r in rows],
    }


async def add_member(
    pool: asyncpg.Pool, ws_slug: str, member_email: str, role: str, actor: AuthUser
) -> dict[str, object]:
    """Ajoute (ou re-rôle) un utilisateur validé et actif comme membre."""
    if role not in _VALID_ROLES:
        raise HTTPException(status_code=422, detail="role invalide : 'owner' ou 'member'")
    async with pool.acquire() as conn:
        ws_key, owner_id = await _resolve_ws(conn, ws_slug)
        _require_manager(actor, owner_id)
        target = await conn.fetchrow(
            "SELECT id, validated, disabled FROM app_user WHERE email = $1",
            member_email,
        )
        if target is None:
            raise HTTPException(status_code=404, detail=f"utilisateur '{member_email}' introuvable")
        if not target["validated"] or target["disabled"]:
            raise HTTPException(
                status_code=422,
                detail=f"utilisateur '{member_email}' non validé ou désactivé",
            )
        await conn.execute(
            """
            INSERT INTO workspace_member (workspace_technical_key, user_id, role)
            VALUES ($1, $2, $3)
            ON CONFLICT (workspace_technical_key, user_id) DO UPDATE SET role = EXCLUDED.role
            """,
            ws_key,
            target["id"],
            role,
        )
    return {"added": True, "workspace_slug": ws_slug, "member_email": member_email, "role": role}


async def remove_member(
    pool: asyncpg.Pool, ws_slug: str, member_email: str, actor: AuthUser
) -> dict[str, object]:
    """Retire un membre du workspace."""
    async with pool.acquire() as conn:
        ws_key, owner_id = await _resolve_ws(conn, ws_slug)
        _require_manager(actor, owner_id)
        target_id: uuid.UUID | None = await conn.fetchval(
            "SELECT id FROM app_user WHERE email = $1", member_email
        )
        if target_id is None:
            raise HTTPException(status_code=404, detail=f"utilisateur '{member_email}' introuvable")
        result = await conn.execute(
            "DELETE FROM workspace_member WHERE workspace_technical_key = $1 AND user_id = $2",
            ws_key,
            target_id,
        )
    return {
        "removed": result != "DELETE 0",
        "workspace_slug": ws_slug,
        "member_email": member_email,
    }

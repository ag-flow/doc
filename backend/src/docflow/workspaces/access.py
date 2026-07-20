from __future__ import annotations

import uuid

import asyncpg

from docflow.schemas.auth import AuthUser


async def user_can_access_workspace(
    conn: asyncpg.Connection, ws_key: uuid.UUID, user: AuthUser
) -> bool:
    """Vrai si ``user`` accède au workspace ``ws_key``.

    Trois voies d'accès (au niveau workspace, unité d'isolation) : superadmin
    (``is_admin``), owner (``workspace.owner_id``) ou membre
    (``workspace_member``). Owner NULL sans membre ⇒ superadmin uniquement.
    """
    if user.is_admin:
        return True
    row = await conn.fetchrow(
        """
        SELECT 1
        FROM workspace w
        WHERE w.workspace_technical_key = $1
          AND (
                w.owner_id = $2
             OR EXISTS (
                    SELECT 1 FROM workspace_member m
                    WHERE m.workspace_technical_key = w.workspace_technical_key
                      AND m.user_id = $2
                )
              )
        """,
        ws_key,
        user.id,
    )
    return row is not None


async def accessible_workspace_slugs(pool: asyncpg.Pool, user: AuthUser) -> set[str] | None:
    """Slugs des workspaces accessibles à ``user`` ; ``None`` = tous (superadmin).

    Un superadmin voit tout : renvoyer ``None`` évite de matérialiser l'ensemble
    complet. Sinon, l'ensemble des workspaces où l'utilisateur est owner ou membre.
    """
    if user.is_admin:
        return None
    rows = await pool.fetch(
        """
        SELECT DISTINCT w.slug
        FROM workspace w
        LEFT JOIN workspace_member m
               ON m.workspace_technical_key = w.workspace_technical_key
              AND m.user_id = $1
        WHERE w.owner_id = $1 OR m.user_id IS NOT NULL
        """,
        user.id,
    )
    return {r["slug"] for r in rows}

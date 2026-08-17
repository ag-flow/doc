from __future__ import annotations

import uuid

import asyncpg
from fastapi import Depends, HTTPException, Request

from docflow.auth.deps import require_authenticated
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


async def require_ws_access(
    request: Request, user: AuthUser = Depends(require_authenticated)
) -> None:
    """Dépendance REST : n'autorise l'accès aux routes `/workspaces/{ws_slug}/…`
    qu'aux utilisateurs ayant accès au workspace (owner / membre / superadmin).

    - Route sans `ws_slug` dans le chemin → no-op (la dépendance peut être posée
      au niveau du router, même mixte).
    - Requête par clé API : ``user`` est le **propriétaire** de la clé (résolu
      par ``get_current_user``) — son accès réel s'applique aussi, EN PLUS des
      scopes de la clé (`check_api_key_scope`). Accès effectif = accès
      propriétaire ∩ scopes de clé, comme `_check_user_access` côté MCP.
    - Workspace inconnu → no-op : les services rendent leur 404 habituel.
    - Sans accès → **404** (fail closed : ne pas révéler l'existence).
    """
    ws_slug = request.path_params.get("ws_slug")
    if not ws_slug:
        return
    if user.is_admin:
        return
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        key = await conn.fetchval(
            "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
        )
        if key is None:
            return
        if not await user_can_access_workspace(conn, key, user):
            raise HTTPException(status_code=404, detail=f"workspace '{ws_slug}' introuvable")

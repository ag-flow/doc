from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.schemas.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate

_COLS = (
    "workspace_technical_key, slug, label, description, owner_id,"
    " archived_at, created_at, updated_at"
)
_SELECT_WS = f"SELECT {_COLS} FROM workspace WHERE slug = $1"
_SELECT_ALL = f"SELECT {_COLS} FROM workspace {{where}} ORDER BY created_at"
_UPDATE_WS = (
    f"UPDATE workspace SET {{cols}}, updated_at = now() WHERE workspace_technical_key = $1 "
    f"RETURNING {_COLS}"
)
_UPDATABLE = frozenset({"label", "description"})


def _row(row: asyncpg.Record) -> WorkspaceOut:
    return WorkspaceOut(
        workspace_technical_key=row["workspace_technical_key"],
        slug=row["slug"],
        label=row["label"],
        description=row["description"],
        owner_id=row["owner_id"],
        archived_at=row["archived_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def list_workspaces(
    pool: asyncpg.Pool, *, include_archived: bool = False
) -> list[WorkspaceOut]:
    where = "" if include_archived else "WHERE archived_at IS NULL"
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SELECT_ALL.format(where=where))
    return [_row(r) for r in rows]


async def get_workspace(pool: asyncpg.Pool, ws_slug: str) -> WorkspaceOut:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT_WS, ws_slug)
    if row is None:
        raise HTTPException(status_code=404, detail=f"workspace '{ws_slug}' introuvable")
    return _row(row)


async def create_workspace(
    pool: asyncpg.Pool, data: WorkspaceCreate, owner_id: uuid.UUID
) -> WorkspaceOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO workspace (slug, label, description, owner_id)
                    VALUES ($1, $2, $3, $4)
                    RETURNING {_COLS}
                    """,
                    data.slug,
                    data.label,
                    data.description,
                    owner_id,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(
                    status_code=409, detail=f"workspace '{data.slug}' existe déjà"
                ) from exc
    assert row is not None
    return _row(row)


async def update_workspace(pool: asyncpg.Pool, ws_slug: str, data: WorkspaceUpdate) -> WorkspaceOut:
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _UPDATABLE}
    if not updates:
        return await get_workspace(pool, ws_slug)
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
            row = await conn.fetchrow(_UPDATE_WS.format(cols=cols), wk, *list(updates.values()))
    assert row is not None
    return _row(row)


async def archive_workspace(pool: asyncpg.Pool, ws_slug: str) -> WorkspaceOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            row = await conn.fetchrow(
                f"UPDATE workspace SET archived_at = now(), updated_at = now() "
                f"WHERE workspace_technical_key = $1 RETURNING {_COLS}",
                wk,
            )
    assert row is not None
    return _row(row)


async def delete_workspace(pool: asyncpg.Pool, ws_slug: str, confirm: str) -> None:
    if confirm != ws_slug:
        raise HTTPException(
            status_code=400,
            detail="confirmation incorrecte : re-saisir le slug exact du workspace",
        )
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            await conn.execute("DELETE FROM workspace WHERE workspace_technical_key = $1", wk)

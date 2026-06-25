from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_type, require_workspace
from docflow.schemas.types import FunctionalTypeCreate, FunctionalTypeOut, FunctionalTypeUpdate

_SELECT_TYPE = """
SELECT ft.id, ft.slug, ft.label, ft.created_at, ft.updated_at,
       p.slug AS parent_slug,
       w.slug AS workspace_slug
FROM functional_type ft
JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key
LEFT JOIN functional_type p ON p.id = ft.parent
WHERE ft.workspace_technical_key = $1 AND ft.slug = $2
"""

_SELECT_ALL = """
SELECT ft.id, ft.slug, ft.label, ft.created_at, ft.updated_at,
       p.slug AS parent_slug,
       w.slug AS workspace_slug
FROM functional_type ft
JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key
LEFT JOIN functional_type p ON p.id = ft.parent
WHERE ft.workspace_technical_key = $1
ORDER BY ft.created_at
"""

_UPDATE_RETURNING = (
    "UPDATE functional_type SET {cols}, updated_at = now() WHERE id = $1 "
    "RETURNING id, slug, label, parent, created_at, updated_at"
)


def _row_to_out(row: asyncpg.Record) -> FunctionalTypeOut:
    return FunctionalTypeOut(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        parent_slug=row["parent_slug"],
        workspace_slug=row["workspace_slug"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _resolve_parent(
    conn: asyncpg.Connection, wk: uuid.UUID, parent_slug: str
) -> uuid.UUID:
    parent_id: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        parent_slug,
    )
    if parent_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"parent '{parent_slug}' introuvable dans ce workspace",
        )
    return parent_id


async def _check_no_cycle(
    conn: asyncpg.Connection, type_id: uuid.UUID, proposed_parent_id: uuid.UUID
) -> None:
    """Vérifie l'absence de cycle si proposed_parent_id devient parent de type_id."""
    if proposed_parent_id == type_id:
        raise HTTPException(
            status_code=422, detail="un type ne peut pas être son propre parent"
        )
    ancestor = proposed_parent_id
    while ancestor is not None:
        row = await conn.fetchrow(
            "SELECT id, parent FROM functional_type WHERE id = $1", ancestor
        )
        if row is None:
            break
        if row["parent"] == type_id:
            raise HTTPException(
                status_code=422, detail="cycle détecté dans la hiérarchie des types"
            )
        ancestor = row["parent"]


async def list_types(pool: asyncpg.Pool, ws_slug: str) -> list[FunctionalTypeOut]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(_SELECT_ALL, wk)
    return [_row_to_out(r) for r in rows]


async def get_type(pool: asyncpg.Pool, ws_slug: str, type_slug: str) -> FunctionalTypeOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(_SELECT_TYPE, wk, type_slug)
    if row is None:
        raise HTTPException(status_code=404, detail=f"type '{type_slug}' introuvable")
    return _row_to_out(row)


async def create_type(
    pool: asyncpg.Pool, ws_slug: str, data: FunctionalTypeCreate
) -> FunctionalTypeOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            parent_id: uuid.UUID | None = None
            if data.parent_slug:
                parent_id = await _resolve_parent(conn, wk, data.parent_slug)
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO functional_type
                        (slug, label, parent, workspace_technical_key)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, slug, label, parent, created_at, updated_at
                    """,
                    data.slug, data.label, parent_id, wk,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"slug '{data.slug}' déjà utilisé dans ce workspace",
                ) from exc
    assert row is not None
    return FunctionalTypeOut(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        parent_slug=data.parent_slug,
        workspace_slug=ws_slug,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def update_type(
    pool: asyncpg.Pool, ws_slug: str, type_slug: str, data: FunctionalTypeUpdate
) -> FunctionalTypeOut:
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        return await get_type(pool, ws_slug, type_slug)

    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            type_id = await require_type(conn, wk, type_slug)

            parent_id: uuid.UUID | None = None
            if "parent_slug" in updates:
                if updates["parent_slug"] is not None:
                    parent_id = await _resolve_parent(conn, wk, updates["parent_slug"])
                    await _check_no_cycle(conn, type_id, parent_id)
                updates["parent"] = parent_id
                del updates["parent_slug"]

            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
            vals = list(updates.values())
            row = await conn.fetchrow(
                _UPDATE_RETURNING.format(cols=cols),
                type_id, *vals,
            )

    assert row is not None
    parent_slug_out: str | None = None
    if row["parent"]:
        parent_slug_out = data.parent_slug
        if parent_slug_out is None:
            async with pool.acquire() as conn:
                parent_slug_out = await conn.fetchval(
                    "SELECT slug FROM functional_type WHERE id = $1", row["parent"]
                )
    return FunctionalTypeOut(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        parent_slug=parent_slug_out,
        workspace_slug=ws_slug,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def delete_type(pool: asyncpg.Pool, ws_slug: str, type_slug: str) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            type_id = await require_type(conn, wk, type_slug)
            try:
                await conn.execute("DELETE FROM functional_type WHERE id = $1", type_id)
            except (asyncpg.ForeignKeyViolationError, asyncpg.RestrictViolationError) as exc:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "impossible de supprimer ce type : "
                        "il a des enfants ou des documents associés"
                    ),
                ) from exc

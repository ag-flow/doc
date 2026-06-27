from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.schemas.block import DataBlockCreate, DataBlockOut, DataBlockUpdate

_SELECT_BLOCK = """
SELECT b.id, b.slug, b.label, b.created_at, b.updated_at, b.exposed,
       ft.slug  AS functional_type_slug,
       p.slug   AS parent_slug,
       w.slug   AS workspace_slug
FROM data_block b
JOIN workspace w ON w.workspace_technical_key = b.workspace_technical_key
JOIN functional_type ft ON ft.id = b.functional_type_ref
LEFT JOIN data_block p ON p.id = b.parent
WHERE b.workspace_technical_key = $1 AND b.slug = $2
"""

_SELECT_ALL = """
SELECT b.id, b.slug, b.label, b.created_at, b.updated_at, b.exposed,
       ft.slug  AS functional_type_slug,
       p.slug   AS parent_slug,
       w.slug   AS workspace_slug
FROM data_block b
JOIN workspace w ON w.workspace_technical_key = b.workspace_technical_key
JOIN functional_type ft ON ft.id = b.functional_type_ref
LEFT JOIN data_block p ON p.id = b.parent
WHERE b.workspace_technical_key = $1
ORDER BY b.created_at
"""


def _row(row: asyncpg.Record) -> DataBlockOut:
    return DataBlockOut(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        functional_type_slug=row["functional_type_slug"],
        parent_slug=row["parent_slug"],
        workspace_slug=row["workspace_slug"],
        exposed=row["exposed"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _resolve_type(
    conn: asyncpg.Connection, wk: uuid.UUID, type_slug: str
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Retourne (type_id, type_parent_id)."""
    row = await conn.fetchrow(
        "SELECT id, parent FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        type_slug,
    )
    if row is None:
        raise HTTPException(
            status_code=422,
            detail=f"type fonctionnel '{type_slug}' introuvable dans ce workspace",
        )
    return row["id"], row["parent"]


async def _check_mirror_constraint(
    conn: asyncpg.Connection,
    wk: uuid.UUID,
    child_type_id: uuid.UUID,
    child_type_parent_id: uuid.UUID | None,
    parent_block_slug: str,
) -> None:
    """I-5 : le type de l'enfant doit être un fils direct du type du parent."""
    parent_row = await conn.fetchrow(
        "SELECT b.functional_type_ref FROM data_block b "
        "WHERE b.workspace_technical_key = $1 AND b.slug = $2",
        wk,
        parent_block_slug,
    )
    if parent_row is None:
        raise HTTPException(
            status_code=422,
            detail=f"bloc parent '{parent_block_slug}' introuvable dans ce workspace",
        )
    parent_type_id: uuid.UUID = parent_row["functional_type_ref"]
    if child_type_parent_id != parent_type_id:
        raise HTTPException(
            status_code=422,
            detail=(
                "contrainte miroir (I-5) : le type du bloc enfant doit être "
                "un fils direct du type du bloc parent"
            ),
        )


async def list_blocks(pool: asyncpg.Pool, ws_slug: str) -> list[DataBlockOut]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(_SELECT_ALL, wk)
    return [_row(r) for r in rows]


async def get_block(pool: asyncpg.Pool, ws_slug: str, block_slug: str) -> DataBlockOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(_SELECT_BLOCK, wk, block_slug)
    if row is None:
        raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
    return _row(row)


async def create_block(pool: asyncpg.Pool, ws_slug: str, data: DataBlockCreate) -> DataBlockOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            type_id, type_parent_id = await _resolve_type(conn, wk, data.functional_type_slug)

            parent_id: uuid.UUID | None = None
            if data.parent_slug is not None:
                await _check_mirror_constraint(conn, wk, type_id, type_parent_id, data.parent_slug)
                parent_id = await conn.fetchval(
                    "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = $2",
                    wk,
                    data.parent_slug,
                )
            else:
                # Bloc racine : le type doit être racine (parent=null dans functional_type)
                if type_parent_id is not None:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "contrainte miroir (I-5) : un bloc racine (sans parent) "
                            "doit avoir un type racine"
                        ),
                    )

            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO data_block
                        (slug, label, functional_type_ref, parent, workspace_technical_key)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, slug, label, created_at, updated_at
                    """,
                    data.slug,
                    data.label,
                    type_id,
                    parent_id,
                    wk,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"slug '{data.slug}' déjà utilisé dans ce workspace",
                ) from exc
    assert row is not None
    return DataBlockOut(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        functional_type_slug=data.functional_type_slug,
        parent_slug=data.parent_slug,
        workspace_slug=ws_slug,
        exposed=False,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def update_block(
    pool: asyncpg.Pool, ws_slug: str, block_slug: str, data: DataBlockUpdate
) -> DataBlockOut:
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        return await get_block(pool, ws_slug, block_slug)

    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            block_row = await conn.fetchrow(
                "SELECT id, functional_type_ref FROM data_block "
                "WHERE workspace_technical_key = $1 AND slug = $2",
                wk,
                block_slug,
            )
            if block_row is None:
                raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
            block_id: uuid.UUID = block_row["id"]
            block_type_id: uuid.UUID = block_row["functional_type_ref"]

            db_updates: dict[str, object] = {}
            if "label" in updates:
                db_updates["label"] = updates["label"]

            if "parent_slug" in updates:
                new_parent_slug = updates["parent_slug"]
                if new_parent_slug is not None:
                    type_parent_id: uuid.UUID | None = await conn.fetchval(
                        "SELECT parent FROM functional_type WHERE id = $1", block_type_id
                    )
                    await _check_mirror_constraint(
                        conn, wk, block_type_id, type_parent_id, new_parent_slug
                    )
                    db_updates["parent"] = await conn.fetchval(
                        "SELECT id FROM data_block "
                        "WHERE workspace_technical_key = $1 AND slug = $2",
                        wk,
                        new_parent_slug,
                    )
                else:
                    db_updates["parent"] = None

            if not db_updates:
                return await get_block(pool, ws_slug, block_slug)

            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(db_updates))
            await conn.execute(
                f"UPDATE data_block SET {cols}, updated_at = now() WHERE id = $1",
                block_id,
                *list(db_updates.values()),
            )

    return await get_block(pool, ws_slug, block_slug)


async def set_block_exposed(
    pool: asyncpg.Pool, ws_slug: str, block_slug: str, value: bool
) -> DataBlockOut:
    """Expose ou masque le bloc entier et tous ses documents (en une transaction)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            block_id: uuid.UUID | None = await conn.fetchval(
                "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = $2",
                wk,
                block_slug,
            )
            if block_id is None:
                raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
            await conn.execute(
                "UPDATE data_block SET exposed = $2, updated_at = now() WHERE id = $1",
                block_id,
                value,
            )
            await conn.execute(
                "UPDATE document SET exposed = $2, updated_at = now() WHERE data_block_ref = $1",
                block_id,
                value,
            )
    return await get_block(pool, ws_slug, block_slug)


async def delete_block(pool: asyncpg.Pool, ws_slug: str, block_slug: str) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            block_id: uuid.UUID | None = await conn.fetchval(
                "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = $2",
                wk,
                block_slug,
            )
            if block_id is None:
                raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
            try:
                await conn.execute("DELETE FROM data_block WHERE id = $1", block_id)
            except (asyncpg.ForeignKeyViolationError, asyncpg.RestrictViolationError) as exc:
                raise HTTPException(
                    status_code=409,
                    detail="impossible de supprimer : ce bloc a des enfants",
                ) from exc

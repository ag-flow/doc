from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.schemas.document import DocumentCreate, DocumentOut, DocumentUpdate

_SELECT_DOC = """
SELECT d.doc_technical_key, d.title, d.type, d.contenu,
       d.parent, d.created_at, d.updated_at,
       ft.slug AS functional_type_slug,
       w.slug  AS workspace_slug
FROM document d
JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
WHERE d.doc_technical_key = $1 AND d.workspace_technical_key = $2
"""

_SELECT_ALL = """
SELECT d.doc_technical_key, d.title, d.type, d.contenu,
       d.parent, d.created_at, d.updated_at,
       ft.slug AS functional_type_slug,
       w.slug  AS workspace_slug
FROM document d
JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
WHERE d.workspace_technical_key = $1
ORDER BY d.created_at
"""

_UPDATE_DOC = (
    "UPDATE document SET {cols}, updated_at = now() WHERE doc_technical_key = $1 "
    "RETURNING doc_technical_key, title, type, contenu, parent, created_at, updated_at"
)

_UPDATABLE = frozenset({"title", "contenu"})


def _row(row: asyncpg.Record) -> DocumentOut:
    return DocumentOut(
        doc_technical_key=row["doc_technical_key"],
        title=row["title"],
        type=row["type"],
        contenu=row["contenu"],
        parent_id=row["parent"],
        functional_type_slug=row["functional_type_slug"],
        workspace_slug=row["workspace_slug"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _resolve_functional_type(
    conn: asyncpg.Connection, wk: uuid.UUID, type_slug: str
) -> uuid.UUID:
    ft_id: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk, type_slug,
    )
    if ft_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"type fonctionnel '{type_slug}' introuvable dans ce workspace",
        )
    return ft_id


async def _validate_parent(
    conn: asyncpg.Connection, wk: uuid.UUID, parent_id: uuid.UUID
) -> None:
    """Vérifie que le parent existe et appartient au même workspace (I-1)."""
    parent_wk: uuid.UUID | None = await conn.fetchval(
        "SELECT workspace_technical_key FROM document WHERE doc_technical_key = $1",
        parent_id,
    )
    if parent_wk is None:
        raise HTTPException(
            status_code=422, detail=f"document parent {parent_id} introuvable"
        )
    if parent_wk != wk:
        raise HTTPException(
            status_code=422,
            detail="le parent doit appartenir au même workspace (I-1)",
        )


async def list_documents(pool: asyncpg.Pool, ws_slug: str) -> list[DocumentOut]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(_SELECT_ALL, wk)
    return [_row(r) for r in rows]


async def get_document(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID
) -> DocumentOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(_SELECT_DOC, doc_id, wk)
    if row is None:
        raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
    return _row(row)


async def create_document(
    pool: asyncpg.Pool, ws_slug: str, data: DocumentCreate
) -> DocumentOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            ft_id: uuid.UUID | None = None
            if data.functional_type_slug:
                ft_id = await _resolve_functional_type(conn, wk, data.functional_type_slug)
            if data.parent_id:
                await _validate_parent(conn, wk, data.parent_id)
            row = await conn.fetchrow(
                """
                INSERT INTO document
                    (title, contenu, parent, functional_type_ref, workspace_technical_key)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING doc_technical_key, title, type, contenu,
                          parent, created_at, updated_at
                """,
                data.title, data.contenu, data.parent_id, ft_id, wk,
            )
    assert row is not None
    ft_slug = data.functional_type_slug
    return DocumentOut(
        doc_technical_key=row["doc_technical_key"],
        title=row["title"],
        type=row["type"],
        contenu=row["contenu"],
        parent_id=row["parent"],
        functional_type_slug=ft_slug,
        workspace_slug=ws_slug,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def update_document(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, data: DocumentUpdate
) -> DocumentOut:
    raw = data.model_dump(exclude_unset=True)
    if not raw:
        return await get_document(pool, ws_slug, doc_id)

    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            exists: uuid.UUID | None = await conn.fetchval(
                "SELECT doc_technical_key FROM document "
                "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
                doc_id, wk,
            )
            if exists is None:
                raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")

            updates: dict[str, object] = {}
            for k, v in raw.items():
                if k in _UPDATABLE:
                    updates[k] = v

            if "parent_id" in raw:
                parent_id = raw["parent_id"]
                if parent_id is not None:
                    await _validate_parent(conn, wk, parent_id)
                updates["parent"] = parent_id

            if "functional_type_slug" in raw:
                ft_slug = raw["functional_type_slug"]
                if ft_slug is not None:
                    updates["functional_type_ref"] = await _resolve_functional_type(
                        conn, wk, ft_slug
                    )
                else:
                    updates["functional_type_ref"] = None

            if not updates:
                return await get_document(pool, ws_slug, doc_id)

            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
            await conn.execute(
                _UPDATE_DOC.format(cols=cols), doc_id, *list(updates.values())
            )

    return await get_document(pool, ws_slug, doc_id)


async def delete_document(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            exists: uuid.UUID | None = await conn.fetchval(
                "SELECT doc_technical_key FROM document "
                "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
                doc_id, wk,
            )
            if exists is None:
                raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
            try:
                await conn.execute(
                    "DELETE FROM document WHERE doc_technical_key = $1", doc_id
                )
            except asyncpg.RestrictViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="impossible de supprimer : ce document a des enfants",
                ) from exc

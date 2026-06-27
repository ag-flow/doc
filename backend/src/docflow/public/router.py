"""Endpoints publics — aucune authentification requise.

Un document est accessible si et seulement si son flag `exposed` est true.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from docflow.schemas.document import DocumentOut

router = APIRouter(tags=["public"])

_SELECT_DOC = """
SELECT d.doc_technical_key, d.title, d.type, d.version,
       d.parent, d.created_at, d.updated_at,
       d.data_block_ref, d.exposed,
       ft.slug AS functional_type_slug,
       w.slug  AS workspace_slug,
       dv.content
FROM document d
JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
LEFT JOIN document_version dv
    ON dv.document_ref = d.doc_technical_key AND dv.version_number = d.version
WHERE d.doc_technical_key = $1 AND d.exposed = true
"""

_SELECT_CHILDREN = """
SELECT d.doc_technical_key, d.title, d.type, d.version,
       d.parent, d.created_at, d.updated_at,
       d.data_block_ref, d.exposed,
       ft.slug AS functional_type_slug,
       w.slug  AS workspace_slug
FROM document d
JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
WHERE d.parent = $1 AND d.exposed = true
ORDER BY d.created_at
"""

_NOT_FOUND = "document introuvable ou non public"


def _map(row: object, content: str | None = None) -> DocumentOut:
    import asyncpg  # noqa: PLC0415

    r: asyncpg.Record = row
    has_content = "content" in r.keys()
    return DocumentOut(
        doc_technical_key=r["doc_technical_key"],
        title=r["title"],
        type=r["type"],
        content=r["content"] if (content is None and has_content) else content,
        version=r["version"],
        parent_id=r["parent"],
        functional_type_slug=r["functional_type_slug"],
        workspace_slug=r["workspace_slug"],
        data_block_ref=r["data_block_ref"],
        exposed=r["exposed"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


@router.get("/documents/{doc_id}", response_model=DocumentOut)
async def get_public_document(doc_id: uuid.UUID, request: Request) -> DocumentOut:
    async with request.app.state.pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT_DOC, doc_id)
    if row is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return _map(row)


@router.get("/documents/{doc_id}/children", response_model=list[DocumentOut])
async def list_public_document_children(doc_id: uuid.UUID, request: Request) -> list[DocumentOut]:
    async with request.app.state.pool.acquire() as conn:
        parent = await conn.fetchrow(_SELECT_DOC, doc_id)
        if parent is None:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        rows = await conn.fetch(_SELECT_CHILDREN, doc_id)
    return [_map(r, content=None) for r in rows]

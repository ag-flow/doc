from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException
from pydantic import BaseModel


class DocLocationOut(BaseModel):
    """Localisation d'un document par son id : de quoi construire son URL."""

    id: uuid.UUID
    title: str
    workspace_slug: str
    block_slug: str | None


async def locate_document(
    pool: asyncpg.Pool,
    doc_id: uuid.UUID,
    *,
    allowed_ws: set[str] | None,
) -> DocLocationOut:
    """Résout un id de document (lien ``docflow://doc/{id}``) en ws/bloc.

    ``allowed_ws=None`` = superadmin. Un document hors des workspaces
    accessibles répond 404 — même réponse qu'un id inconnu, aucun oracle
    d'existence (fail closed).
    """
    if allowed_ws is not None and not allowed_ws:
        raise HTTPException(status_code=404, detail="DocumentNotFound")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT d.doc_technical_key AS id,
                   d.title,
                   w.slug AS workspace_slug,
                   b.slug AS block_slug
            FROM document d
            JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
            LEFT JOIN data_block b ON b.id = d.data_block_ref
            WHERE d.doc_technical_key = $1
              AND ($2::text[] IS NULL OR w.slug = ANY($2::text[]))
            """,
            doc_id,
            sorted(allowed_ws) if allowed_ws is not None else None,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="DocumentNotFound")
    return DocLocationOut(
        id=row["id"],
        title=row["title"],
        workspace_slug=row["workspace_slug"],
        block_slug=row["block_slug"],
    )

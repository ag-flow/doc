from __future__ import annotations

import uuid

import asyncpg
from pydantic import BaseModel

from docflow.db.helpers import require_workspace
from docflow.references.parser import extract_references

# ── DTOs ─────────────────────────────────────────────────────────────────────


class DocumentSearchResult(BaseModel):
    id: uuid.UUID
    title: str
    type: str | None
    bloc: uuid.UUID | None


class BrokenLinkBloc(BaseModel):
    bloc: uuid.UUID | None
    docs_with_broken_links: int


class BrokenLinkDetail(BaseModel):
    source_ref: uuid.UUID
    source_title: str
    target_ref: uuid.UUID | None
    target_label: str


class BacklinkOut(BaseModel):
    source_id: uuid.UUID
    source_title: str
    source_type: str | None
    bloc: uuid.UUID | None
    target_label: str


# ── Rafraîchissement des références (appelé dans la transaction du save) ─────


async def refresh_references(
    conn: asyncpg.Connection,
    doc_id: uuid.UUID,
    ws_key: uuid.UUID,
    content: str | None,
) -> None:
    """Remplace toutes les références du document.

    Doit être appelé dans la même transaction que le bump de version.
    La table est reconstruite à partir du contenu courant ; un lien retiré
    disparaît donc de la table au save suivant.
    """
    refs = extract_references(content or "")
    await conn.execute("DELETE FROM document_reference WHERE source_ref = $1", doc_id)
    if refs:
        await conn.executemany(
            """INSERT INTO document_reference
                   (source_ref, target_ref, target_label, workspace_technical_key)
               VALUES ($1, $2, $3, $4)""",
            [(doc_id, uuid.UUID(tid), label, ws_key) for tid, label in refs.items()],
        )


# ── Recherche de documents par titre ─────────────────────────────────────────


async def search_documents(
    pool: asyncpg.Pool,
    ws_slug: str,
    q: str,
    limit: int,
) -> list[DocumentSearchResult]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT d.doc_technical_key AS id,
                   d.title,
                   ft.slug             AS type,
                   d.data_block_ref    AS bloc
            FROM document d
            LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
            WHERE d.workspace_technical_key = $1
              AND d.title ILIKE '%' || $2 || '%'
            ORDER BY similarity(d.title, $2) DESC
            LIMIT $3
            """,
            wk,
            q,
            limit,
        )
    return [
        DocumentSearchResult(
            id=r["id"],
            title=r["title"],
            type=r["type"],
            bloc=r["bloc"],
        )
        for r in rows
    ]


# ── Détection d'orphelins ─────────────────────────────────────────────────────


async def broken_links_by_bloc(
    pool: asyncpg.Pool,
    ws_slug: str,
) -> list[BrokenLinkBloc]:
    """Agrégat par bloc : nombre de documents ayant ≥1 référence orpheline."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT src.data_block_ref                   AS bloc,
                   count(DISTINCT r.source_ref)::int    AS docs_with_broken_links
            FROM document_reference r
            JOIN document src        ON src.doc_technical_key = r.source_ref
            LEFT JOIN document target ON target.doc_technical_key = r.target_ref
            WHERE r.workspace_technical_key = $1
              AND target.doc_technical_key IS NULL
            GROUP BY src.data_block_ref
            """,
            wk,
        )
    return [
        BrokenLinkBloc(bloc=r["bloc"], docs_with_broken_links=r["docs_with_broken_links"])
        for r in rows
    ]


async def get_backlinks(
    pool: asyncpg.Pool,
    ws_slug: str,
    doc_id: uuid.UUID,
    limit: int = 50,
) -> list[BacklinkOut]:
    """Références inverses : documents qui citent doc_id dans ce workspace."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT r.source_ref            AS source_id,
                   src.title               AS source_title,
                   ft.slug                 AS source_type,
                   src.data_block_ref      AS bloc,
                   r.target_label
            FROM document_reference r
            JOIN document src         ON src.doc_technical_key = r.source_ref
            LEFT JOIN functional_type ft ON ft.id = src.functional_type_ref
            WHERE r.target_ref = $1
              AND r.workspace_technical_key = $2
            ORDER BY src.title
            LIMIT $3
            """,
            doc_id,
            wk,
            limit,
        )
    return [
        BacklinkOut(
            source_id=r["source_id"],
            source_title=r["source_title"],
            source_type=r["source_type"],
            bloc=r["bloc"],
            target_label=r["target_label"],
        )
        for r in rows
    ]


async def broken_links_detail(
    pool: asyncpg.Pool,
    ws_slug: str,
    bloc_id: uuid.UUID,
) -> list[BrokenLinkDetail]:
    """Détail des liens cassés d'un bloc : document source + libellé de la cible disparue."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT r.source_ref,
                   src.title   AS source_title,
                   r.target_ref,
                   r.target_label
            FROM document_reference r
            JOIN document src         ON src.doc_technical_key = r.source_ref
            LEFT JOIN document target  ON target.doc_technical_key = r.target_ref
            WHERE r.workspace_technical_key = $1
              AND src.data_block_ref = $2
              AND target.doc_technical_key IS NULL
            ORDER BY src.title
            """,
            wk,
            bloc_id,
        )
    return [
        BrokenLinkDetail(
            source_ref=r["source_ref"],
            source_title=r["source_title"],
            target_ref=r["target_ref"],
            target_label=r["target_label"],
        )
        for r in rows
    ]

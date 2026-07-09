"""Listing paginé des objets d'un bloc et query filtrée paginée (épic MCP docflow).

Deux primitives, pagination obligatoire (contrainte de conception : ces requêtes
peuvent ramener de gros volumes) :
  - list_block_objects : les documents d'un bloc avec leurs valeurs de propriétés ;
  - query_documents    : ceux qui matchent un filtre sur une ou plusieurs propriétés.
"""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.schemas.introspection import (
    BlockObjectOut,
    BlockObjectsPage,
    PropertyValueBrief,
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

_LOAD_VALUES = """
SELECT pv.document_ref,
       pd.slug  AS prop_slug,
       pd.type  AS prop_type,
       pvv.value,
       pav.slug  AS allowed_value_slug,
       pav.label AS allowed_value_label
FROM properties_values pv
JOIN properties_defs pd ON pd.id = pv.property_def_ref
JOIN properties_value_version pvv
    ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
WHERE pv.document_ref = ANY($1::uuid[])
ORDER BY pd.slug
"""


def _normalize_pagination(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise HTTPException(status_code=422, detail="page doit être >= 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=422, detail=f"page_size doit être entre 1 et {MAX_PAGE_SIZE}"
        )
    return page, page_size


async def _resolve_block(conn: asyncpg.Connection, wk: uuid.UUID, block_slug: str) -> uuid.UUID:
    block_id: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        block_slug,
    )
    if block_id is None:
        raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
    return block_id


async def _load_values(
    conn: asyncpg.Connection, doc_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[PropertyValueBrief]]:
    if not doc_ids:
        return {}
    rows = await conn.fetch(_LOAD_VALUES, doc_ids)
    by_doc: dict[uuid.UUID, list[PropertyValueBrief]] = {}
    for r in rows:
        by_doc.setdefault(r["document_ref"], []).append(
            PropertyValueBrief(
                prop_slug=r["prop_slug"],
                type=r["prop_type"],
                value=r["value"],
                allowed_value_slug=r["allowed_value_slug"],
                allowed_value_label=r["allowed_value_label"],
            )
        )
    return by_doc


async def _assemble_page(
    conn: asyncpg.Connection,
    block_slug: str,
    docs: list[asyncpg.Record],
    total: int,
    page: int,
    page_size: int,
) -> BlockObjectsPage:
    doc_ids = [d["id"] for d in docs]
    values = await _load_values(conn, doc_ids)
    objects = [
        BlockObjectOut(
            id=str(d["id"]),
            title=d["title"],
            functional_type_slug=d["functional_type_slug"],
            properties=values.get(d["id"], []),
        )
        for d in docs
    ]
    return BlockObjectsPage(
        block_slug=block_slug,
        page=page,
        page_size=page_size,
        total=total,
        has_next=page * page_size < total,
        objects=objects,
    )


_SELECT_DOCS = """
SELECT d.doc_technical_key AS id, d.title, ft.slug AS functional_type_slug
FROM document d
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
WHERE d.data_block_ref = $1{extra}
ORDER BY d.title, d.doc_technical_key
LIMIT $2 OFFSET $3
"""


async def list_block_objects(
    pool: asyncpg.Pool,
    ws_slug: str,
    block_slug: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> BlockObjectsPage:
    page, page_size = _normalize_pagination(page, page_size)
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        block_id = await _resolve_block(conn, wk, block_slug)
        total: int = await conn.fetchval(
            "SELECT count(*) FROM document WHERE data_block_ref = $1", block_id
        )
        docs = await conn.fetch(
            _SELECT_DOCS.format(extra=""),
            block_id,
            page_size,
            (page - 1) * page_size,
        )
        return await _assemble_page(conn, block_slug, docs, total, page, page_size)


def _build_filter_sql(filters: dict[str, str], start_param: int) -> tuple[str, list[str]]:
    """Construit les clauses EXISTS paramétrées (AND) et la liste des paramètres.

    Une clause matche indifféremment une restricted_list (par slug de valeur autorisée)
    ou un scalaire (par value brute) : ``(pav.slug = $x OR pvv.value = $x)``.
    """
    clauses: list[str] = []
    params: list[str] = []
    p = start_param
    for prop_slug, expected in filters.items():
        clauses.append(
            f"""
            AND EXISTS (
                SELECT 1 FROM properties_values pv
                JOIN properties_defs pd ON pd.id = pv.property_def_ref
                JOIN properties_value_version pvv
                    ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
                LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
                WHERE pv.document_ref = d.doc_technical_key
                  AND pd.slug = ${p}
                  AND (pav.slug = ${p + 1} OR pvv.value = ${p + 1})
            )"""
        )
        params.extend([prop_slug, expected])
        p += 2
    return "".join(clauses), params


async def query_documents(
    pool: asyncpg.Pool,
    ws_slug: str,
    block_slug: str,
    filters: dict[str, str],
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> BlockObjectsPage:
    page, page_size = _normalize_pagination(page, page_size)
    if not filters:
        raise HTTPException(
            status_code=422,
            detail="au moins un filtre (prop_slug → valeur attendue) est requis",
        )
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        block_id = await _resolve_block(conn, wk, block_slug)
        # $1 = block_id ; filtres à partir de $2 pour le count, $2/$3 réservés au
        # LIMIT/OFFSET dans la requête paginée → filtres à partir de $4.
        count_where, count_params = _build_filter_sql(filters, 2)
        total: int = await conn.fetchval(
            f"SELECT count(*) FROM document d WHERE d.data_block_ref = $1{count_where}",
            block_id,
            *count_params,
        )
        page_where, page_params = _build_filter_sql(filters, 4)
        docs = await conn.fetch(
            _SELECT_DOCS.format(extra=page_where),
            block_id,
            page_size,
            (page - 1) * page_size,
            *page_params,
        )
        return await _assemble_page(conn, block_slug, docs, total, page, page_size)

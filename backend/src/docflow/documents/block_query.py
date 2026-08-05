"""Listing paginé des objets d'un bloc et moteur de requête (QuerySpec).

Deux primitives, pagination obligatoire :
  - list_block_objects : les documents d'un bloc avec leurs valeurs de propriétés ;
  - query_documents    : moteur générique piloté par un QuerySpec (filtres typés,
                         tri multi-clé, projection, sélection par type, pagination).

Tout le SQL dynamique est **100 % paramétré** via l'accumulateur `_Params` : aucun
slug ni valeur n'est interpolé dans la chaîne (surface d'injection nulle).
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
from docflow.schemas.query import OPS_BY_TYPE, FilterClause, QuerySpec, SortKey

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
  AND ($2::text[] IS NULL OR pd.slug = ANY($2::text[]))
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
    conn: asyncpg.Connection,
    doc_ids: list[uuid.UUID],
    projection: list[str] | None = None,
) -> dict[uuid.UUID, list[PropertyValueBrief]]:
    if not doc_ids:
        return {}
    rows = await conn.fetch(_LOAD_VALUES, doc_ids, projection)
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
    projection: list[str] | None = None,
) -> BlockObjectsPage:
    doc_ids = [d["id"] for d in docs]
    values = await _load_values(conn, doc_ids, projection)
    objects = [
        BlockObjectOut(
            id=str(d["id"]),
            title=d["title"],
            functional_type_slug=d["functional_type_slug"],
            updated_at=d["updated_at"] if "updated_at" in d.keys() else None,
            updated_by=d["updated_by"] if "updated_by" in d.keys() else None,
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
SELECT d.doc_technical_key AS id, d.title, ft.slug AS functional_type_slug,
       d.updated_at, d.updated_by
FROM document d
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
WHERE d.data_block_ref = $1
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
            _SELECT_DOCS,
            block_id,
            page_size,
            (page - 1) * page_size,
        )
        return await _assemble_page(conn, block_slug, docs, total, page, page_size)


# ── Moteur de requête (QuerySpec) ──────────────────────────────────────────────


class _Params:
    """Accumulateur de paramètres SQL : chaque add() renvoie le placeholder ($n)."""

    def __init__(self) -> None:
        self.values: list[object] = []

    def add(self, v: object) -> str:
        self.values.append(v)
        return f"${len(self.values)}"


_PROP_TYPES_SQL = """
WITH RECURSIVE subtree AS (
    SELECT ft.id
    FROM data_block b JOIN functional_type ft ON ft.id = b.functional_type_ref
    WHERE b.workspace_technical_key = $1 AND b.slug = $2
    UNION ALL
    SELECT c.id FROM functional_type c JOIN subtree s ON c.parent = s.id
)
SELECT DISTINCT pd.slug, pd.type
FROM properties_defs pd JOIN subtree s ON s.id = pd.functional_type_ref
WHERE pd.slug = ANY($3::text[])
"""


async def _resolve_prop_types(
    conn: asyncpg.Connection, wk: uuid.UUID, block_slug: str, slugs: list[str]
) -> dict[str, str]:
    """Type de données de chaque propriété référencée, résolu sur les types du bloc.

    422 si une propriété est inconnue du bloc ou ambiguë (types de données divergents).
    """
    if not slugs:
        return {}
    rows = await conn.fetch(_PROP_TYPES_SQL, wk, block_slug, slugs)
    by_slug: dict[str, set[str]] = {}
    for r in rows:
        by_slug.setdefault(r["slug"], set()).add(r["type"])
    resolved: dict[str, str] = {}
    for slug in slugs:
        types = by_slug.get(slug)
        if not types:
            raise HTTPException(status_code=422, detail=f"propriété '{slug}' inconnue dans ce bloc")
        if len(types) > 1:
            joined = ", ".join(sorted(types))
            raise HTTPException(
                status_code=422,
                detail=f"propriété '{slug}' ambiguë (types divergents : {joined})",
            )
        resolved[slug] = next(iter(types))
    return resolved


def _cond_sql(c: FilterClause, ptype: str, p: _Params) -> str:
    """Condition SQL d'un filtre, selon le type de la propriété. Paramétrée."""
    op = c.op
    if ptype == "restricted_list":
        if op == "eq":
            return f"pav.slug = {p.add(c.value)}"
        if op == "in":
            return f"pav.slug = ANY({p.add(c.values)}::text[])"
    elif ptype in ("int", "float"):
        # `::text::` force asyncpg à envoyer le paramètre en texte (sinon il infère
        # le type de la cible du cast et rejette la str) ; Postgres caste ensuite.
        col = "pvv.value::numeric"
        if op == "eq":
            return f"{col} = {p.add(c.value)}::text::numeric"
        if op == "lt":
            return f"{col} < {p.add(c.value)}::text::numeric"
        if op == "gt":
            return f"{col} > {p.add(c.value)}::text::numeric"
        if op == "between":
            assert c.values is not None
            lo = f"{p.add(c.values[0])}::text::numeric"
            hi = f"{p.add(c.values[1])}::text::numeric"
            return f"{col} BETWEEN {lo} AND {hi}"
    elif ptype == "date":
        col = "pvv.value::date"
        if op == "eq":
            return f"{col} = {p.add(c.value)}::text::date"
        if op == "before":
            return f"{col} < {p.add(c.value)}::text::date"
        if op == "after":
            return f"{col} > {p.add(c.value)}::text::date"
        if op == "between":
            assert c.values is not None
            lo = f"{p.add(c.values[0])}::text::date"
            hi = f"{p.add(c.values[1])}::text::date"
            return f"{col} BETWEEN {lo} AND {hi}"
    elif ptype in ("text", "url"):
        if op == "eq":
            return f"pvv.value = {p.add(c.value)}"
        if op == "contains":
            return f"strpos(lower(pvv.value), lower({p.add(c.value)})) > 0"
        if op == "starts_with":
            v = p.add(c.value)
            return f"left(lower(pvv.value), length({v})) = lower({v})"
    elif ptype in ("bool", "reference"):
        if op == "eq":
            return f"pvv.value = {p.add(c.value)}"
    raise HTTPException(
        status_code=422, detail=f"opérateur '{op}' non supporté pour le type '{ptype}'"
    )


def _filter_sql(c: FilterClause, ptype: str, p: _Params) -> str:
    prop_ph = p.add(c.prop)
    cond = _cond_sql(c, ptype, p)
    return f"""EXISTS (
        SELECT 1 FROM properties_values pv
        JOIN properties_defs pd ON pd.id = pv.property_def_ref
        JOIN properties_value_version pvv
            ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
        LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
        WHERE pv.document_ref = d.doc_technical_key AND pd.slug = {prop_ph} AND {cond})"""


def _sort_expr(ptype: str) -> str:
    if ptype == "restricted_list":
        return "pav.position"  # tri par ordre du pipeline, pas alphabétique
    if ptype in ("int", "float"):
        return "pvv.value::numeric"
    if ptype == "date":
        return "pvv.value::date"
    return "pvv.value"


def _order_sql(sort: list[SortKey], ptypes: dict[str, str], p: _Params) -> str:
    terms: list[str] = []
    for s in sort:
        direction = "DESC" if s.dir == "desc" else "ASC"
        if s.key == "title":
            terms.append(f"d.title {direction}")
        elif s.key == "created_at":
            terms.append(f"d.created_at {direction}")
        elif s.key == "updated_at":
            terms.append(f"d.updated_at {direction} NULLS LAST")
        else:
            expr = _sort_expr(ptypes[s.key])
            key_ph = p.add(s.key)
            sub = (
                f"(SELECT {expr} FROM properties_values pv "
                "JOIN properties_defs pd ON pd.id = pv.property_def_ref "
                "JOIN properties_value_version pvv "
                "ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version "
                "LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref "
                f"WHERE pv.document_ref = d.doc_technical_key AND pd.slug = {key_ph} LIMIT 1)"
            )
            terms.append(f"{sub} {direction} NULLS LAST")
    terms.append("d.doc_technical_key ASC")  # tie-break stable
    return "ORDER BY " + ", ".join(terms)


async def query_documents(pool: asyncpg.Pool, ws_slug: str, spec: QuerySpec) -> BlockObjectsPage:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        block_id = await _resolve_block(conn, wk, spec.block_slug)

        # Résolution des types + validation op↔type.
        referenced = {f.prop for f in spec.filters}
        referenced |= {
            s.key for s in spec.sort if s.key not in ("title", "created_at", "updated_at")
        }
        ptypes = await _resolve_prop_types(conn, wk, spec.block_slug, sorted(referenced))
        for f in spec.filters:
            allowed = OPS_BY_TYPE.get(ptypes[f.prop], frozenset())
            if f.op not in allowed:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"opérateur '{f.op}' invalide pour '{f.prop}' (type {ptypes[f.prop]}) ; "
                        f"autorisés : {', '.join(sorted(allowed)) or '(aucun)'}"
                    ),
                )

        # WHERE paramétré.
        p = _Params()
        where = [f"d.data_block_ref = {p.add(block_id)}"]
        if spec.type_slugs:
            wk_ph = p.add(wk)
            ts_ph = p.add(spec.type_slugs)
            where.append(
                "d.functional_type_ref IN (SELECT id FROM functional_type "
                f"WHERE workspace_technical_key = {wk_ph} AND slug = ANY({ts_ph}::text[]))"
            )
        for f in spec.filters:
            where.append(_filter_sql(f, ptypes[f.prop], p))
        where_sql = " AND ".join(where)

        total: int = await conn.fetchval(
            f"SELECT count(*) FROM document d WHERE {where_sql}", *p.values
        )

        order_sql = _order_sql(spec.sort, ptypes, p)
        limit_ph = p.add(spec.page_size)
        offset_ph = p.add((spec.page - 1) * spec.page_size)
        docs = await conn.fetch(
            f"SELECT d.doc_technical_key AS id, d.title, ft.slug AS functional_type_slug, "
            f"d.updated_at, d.updated_by "
            "FROM document d LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref "
            f"WHERE {where_sql} {order_sql} LIMIT {limit_ph} OFFSET {offset_ph}",
            *p.values,
        )
        return await _assemble_page(
            conn, spec.block_slug, docs, total, spec.page, spec.page_size, spec.projection
        )

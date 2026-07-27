"""Requêtage d'un dataset par cellule (filtres sur ombres typées, tri, pagination).

Les filtres portent sur l'OMBRE TYPÉE de la colonne (``num_value`` / ``date_value``
/ ``bool_value`` / ``value``). Tout est paramétré (``$1..$n``) : aucune valeur ni
aucun slug n'est interpolé dans le SQL — le slug est validé puis résolu en
``column_ref`` avant usage.
"""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.datasets.coercion import coerce_cell
from docflow.datasets.service import _columns_by_slug, _require_dataset
from docflow.db.helpers import require_workspace, validate_slug

_DEFAULT_PAGE_SIZE = 50

# op → opérateur SQL de comparaison (contains est traité à part en ILIKE).
_COMPARATORS = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}

_NUMERIC_TYPES = ("int", "float")


class _Params:
    """Accumulateur de paramètres SQL positionnels ($1..$n)."""

    def __init__(self) -> None:
        self.values: list[object] = []

    def add(self, value: object) -> str:
        self.values.append(value)
        return f"${len(self.values)}"


def _shadow_for(col_type: str) -> str:
    if col_type in _NUMERIC_TYPES:
        return "num_value"
    if col_type == "date":
        return "date_value"
    if col_type == "bool":
        return "bool_value"
    return "value"


def _filter_clause(col: asyncpg.Record, op: str, raw_value: object, params: _Params) -> str:
    """Construit un EXISTS paramétré pour un filtre sur l'ombre typée d'une colonne."""
    col_type = col["type"]
    shadow = _shadow_for(col_type)
    col_ref = params.add(col["id"])
    if op == "contains":
        if col_type not in ("text", "url"):
            raise HTTPException(
                status_code=422, detail="opérateur 'contains' réservé aux colonnes text/url"
            )
        pattern = params.add(f"%{raw_value}%")
        cond = f"c.value ILIKE {pattern}"
    elif op in _COMPARATORS:
        if col_type == "bool" and op not in ("eq", "neq"):
            raise HTTPException(
                status_code=422, detail="colonne bool : seuls eq/neq sont autorisés"
            )
        if shadow == "value":
            bound = params.add(str(raw_value))
        else:
            bound = params.add(_coerce_filter_value(col_type, raw_value))
        cond = f"c.{shadow} {_COMPARATORS[op]} {bound}"
    else:
        raise HTTPException(status_code=422, detail=f"opérateur de filtre inconnu : '{op}'")
    return (
        f"EXISTS (SELECT 1 FROM dataset_cell c "
        f"WHERE c.row_ref = r.id AND c.column_ref = {col_ref} AND {cond})"
    )


def _coerce_filter_value(col_type: str, raw_value: object) -> object:
    shadow = _shadow_for(col_type)
    try:
        cell = coerce_cell(col_type, str(raw_value))  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"valeur de filtre invalide : {e}") from None
    return cell[shadow]


def _build_where(
    dataset_id: uuid.UUID,
    columns: dict[str, asyncpg.Record],
    filters: list[dict[str, object]],
    params: _Params,
) -> str:
    clauses = [f"r.dataset_ref = {params.add(dataset_id)}"]
    for flt in filters:
        col_slug = validate_slug(str(flt.get("column", "")), "column")
        col = columns.get(col_slug)
        if col is None:
            raise HTTPException(
                status_code=422, detail=f"colonne '{col_slug}' inconnue dans ce dataset"
            )
        op = str(flt.get("op", ""))
        clauses.append(_filter_clause(col, op, flt.get("value"), params))
    return " AND ".join(clauses)


def _order_clause(
    sort: dict[str, object] | None,
    columns: dict[str, asyncpg.Record],
    params: _Params,
) -> tuple[str, str]:
    """Retourne (select_extra, order_by). Tri par l'ombre typée de la colonne."""
    if not sort:
        return "", "ORDER BY r.position, r.id"
    col_slug = validate_slug(str(sort.get("column", "")), "column")
    col = columns.get(col_slug)
    if col is None:
        raise HTTPException(
            status_code=422, detail=f"colonne de tri '{col_slug}' inconnue dans ce dataset"
        )
    direction = "DESC" if str(sort.get("dir", "asc")).lower() == "desc" else "ASC"
    shadow = _shadow_for(col["type"])
    col_ref = params.add(col["id"])
    select_extra = (
        f", (SELECT c.{shadow} FROM dataset_cell c "
        f"WHERE c.row_ref = r.id AND c.column_ref = {col_ref}) AS sort_key"
    )
    order_by = f"ORDER BY sort_key {direction} NULLS LAST, r.position, r.id"
    return select_extra, order_by


async def _load_cells(
    conn: asyncpg.Connection, dataset_id: uuid.UUID, row_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, object]]:
    if not row_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT cell.row_ref, col.slug AS col_slug, cell.value
        FROM dataset_cell cell
        JOIN dataset_column col ON col.id = cell.column_ref
        WHERE col.dataset_ref = $1 AND cell.row_ref = ANY($2::uuid[])
        """,
        dataset_id,
        row_ids,
    )
    by_row: dict[uuid.UUID, dict[str, object]] = {}
    for r in rows:
        by_row.setdefault(r["row_ref"], {})[r["col_slug"]] = r["value"]
    return by_row


async def query_dataset(
    pool: asyncpg.Pool,
    ws_slug: str,
    dataset_id: uuid.UUID,
    filters: list[dict[str, object]] | None = None,
    sort: dict[str, object] | None = None,
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, object]:
    filters = filters or []
    page = max(1, page)
    page_size = max(1, page_size)
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        await _require_dataset(conn, wk, dataset_id)
        columns = await _columns_by_slug(conn, dataset_id)

        where_params = _Params()
        where = _build_where(dataset_id, columns, filters, where_params)
        total = await conn.fetchval(
            f"SELECT count(*) FROM dataset_row r WHERE {where}", *where_params.values
        )

        params = _Params()
        where = _build_where(dataset_id, columns, filters, params)
        select_extra, order_by = _order_clause(sort, columns, params)
        limit = params.add(page_size)
        offset = params.add((page - 1) * page_size)
        row_rows = await conn.fetch(
            f"SELECT r.id{select_extra} FROM dataset_row r "
            f"WHERE {where} {order_by} LIMIT {limit} OFFSET {offset}",
            *params.values,
        )
        row_ids = [r["id"] for r in row_rows]
        cells_by_row = await _load_cells(conn, dataset_id, row_ids)

    return {
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "rows": [{"id": str(rid), "cells": cells_by_row.get(rid, {})} for rid in row_ids],
    }

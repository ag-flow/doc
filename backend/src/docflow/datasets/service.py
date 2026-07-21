"""Service datasets tabulaires : CRUD dataset / colonnes / lignes / cellules.

Chaque fonction résout le workspace (``require_workspace``) puis vérifie que le
dataset appartient bien à ce workspace (404 sinon). Les cellules sont projetées
sur leurs OMBRES TYPÉES via ``coerce_cell`` (module ``coercion``, pur). Le
requêtage par cellule vit dans ``query.py``.
"""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.datasets.coercion import COLUMN_TYPES, coerce_cell
from docflow.db.helpers import require_workspace, validate_slug

_SHADOW_COLS = ("value", "num_value", "date_value", "bool_value")


async def _require_dataset(
    conn: asyncpg.Connection, wk: uuid.UUID, dataset_id: uuid.UUID
) -> asyncpg.Record:
    """Charge le dataset et vérifie son appartenance au workspace ``wk`` (404)."""
    row = await conn.fetchrow(
        "SELECT id, slug, label FROM dataset WHERE id = $1 AND workspace_technical_key = $2",
        dataset_id,
        wk,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"dataset '{dataset_id}' introuvable")
    return row


async def _columns_by_slug(
    conn: asyncpg.Connection, dataset_id: uuid.UUID
) -> dict[str, asyncpg.Record]:
    """Colonnes du dataset indexées par slug (id, slug, label, type, position, required)."""
    rows = await conn.fetch(
        "SELECT id, slug, label, type, position, required FROM dataset_column "
        "WHERE dataset_ref = $1 ORDER BY position, slug",
        dataset_id,
    )
    return {r["slug"]: r for r in rows}


def _require_column(columns: dict[str, asyncpg.Record], slug: str) -> asyncpg.Record:
    col = columns.get(slug)
    if col is None:
        raise HTTPException(status_code=422, detail=f"colonne '{slug}' inconnue dans ce dataset")
    return col


def _coerce_or_422(col_type: str, raw: str | None, col_slug: str) -> dict[str, object]:
    try:
        return coerce_cell(col_type, raw)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"colonne '{col_slug}' : {e}") from None


async def create_dataset(
    pool: asyncpg.Pool,
    ws_slug: str,
    slug: str,
    label: str,
    created_by: uuid.UUID | None,
) -> dict[str, object]:
    validate_slug(slug)
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug, allow_archived=False)
        try:
            row = await conn.fetchrow(
                "INSERT INTO dataset (workspace_technical_key, slug, label, created_by) "
                "VALUES ($1, $2, $3, $4) RETURNING id, slug, label",
                wk,
                slug,
                label,
                created_by,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(
                status_code=409, detail=f"dataset '{slug}' existe déjà dans ce workspace"
            ) from None
    assert row is not None
    return {"id": str(row["id"]), "slug": row["slug"], "label": row["label"]}


async def list_datasets(pool: asyncpg.Pool, ws_slug: str) -> list[dict[str, object]]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT d.id, d.slug, d.label,
                   (SELECT count(*) FROM dataset_column c WHERE c.dataset_ref = d.id)
                       AS column_count,
                   (SELECT count(*) FROM dataset_row r WHERE r.dataset_ref = d.id)
                       AS row_count
            FROM dataset d
            WHERE d.workspace_technical_key = $1
            ORDER BY d.slug
            """,
            wk,
        )
    return [
        {
            "id": str(r["id"]),
            "slug": r["slug"],
            "label": r["label"],
            "column_count": int(r["column_count"]),
            "row_count": int(r["row_count"]),
        }
        for r in rows
    ]


async def get_dataset(pool: asyncpg.Pool, ws_slug: str, dataset_id: uuid.UUID) -> dict[str, object]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        ds = await _require_dataset(conn, wk, dataset_id)
        columns = await _columns_by_slug(conn, dataset_id)
        row_rows = await conn.fetch(
            "SELECT id FROM dataset_row WHERE dataset_ref = $1 ORDER BY position, id",
            dataset_id,
        )
        cell_rows = await conn.fetch(
            """
            SELECT cell.row_ref, col.slug AS col_slug, cell.value
            FROM dataset_cell cell
            JOIN dataset_column col ON col.id = cell.column_ref
            WHERE col.dataset_ref = $1
            """,
            dataset_id,
        )
    cells_by_row: dict[uuid.UUID, dict[str, object]] = {}
    for c in cell_rows:
        cells_by_row.setdefault(c["row_ref"], {})[c["col_slug"]] = c["value"]
    return {
        "id": str(ds["id"]),
        "slug": ds["slug"],
        "label": ds["label"],
        "columns": [
            {
                "slug": col["slug"],
                "label": col["label"],
                "type": col["type"],
                "position": col["position"],
                "required": col["required"],
            }
            for col in columns.values()
        ],
        "rows": [{"id": str(r["id"]), "cells": cells_by_row.get(r["id"], {})} for r in row_rows],
    }


async def add_column(
    pool: asyncpg.Pool,
    ws_slug: str,
    dataset_id: uuid.UUID,
    slug: str,
    label: str,
    type: str,
    position: int | None = None,
    required: bool = False,
) -> dict[str, object]:
    validate_slug(slug)
    if type not in COLUMN_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"type de colonne '{type}' inconnu (attendu : {', '.join(COLUMN_TYPES)})",
        )
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug, allow_archived=False)
        await _require_dataset(conn, wk, dataset_id)
        if position is None:
            position = await conn.fetchval(
                "SELECT coalesce(max(position) + 1, 0) FROM dataset_column WHERE dataset_ref = $1",
                dataset_id,
            )
        try:
            row = await conn.fetchrow(
                "INSERT INTO dataset_column "
                "(dataset_ref, slug, label, type, position, required) "
                "VALUES ($1, $2, $3, $4, $5, $6) "
                "RETURNING id, slug, label, type, position, required",
                dataset_id,
                slug,
                label,
                type,
                position,
                required,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(
                status_code=409, detail=f"colonne '{slug}' existe déjà dans ce dataset"
            ) from None
    assert row is not None
    return dict(row) | {"id": str(row["id"])}


async def update_column(
    pool: asyncpg.Pool,
    ws_slug: str,
    dataset_id: uuid.UUID,
    column_slug: str,
    label: str | None = None,
    type: str | None = None,
    position: int | None = None,
    required: bool | None = None,
) -> dict[str, object]:
    if type is not None and type not in COLUMN_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"type de colonne '{type}' inconnu (attendu : {', '.join(COLUMN_TYPES)})",
        )
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug, allow_archived=False)
        await _require_dataset(conn, wk, dataset_id)
        columns = await _columns_by_slug(conn, dataset_id)
        col = _require_column(columns, column_slug)
        new_type = type if type is not None else col["type"]
        async with conn.transaction():
            if type is not None and type != col["type"]:
                await _retype_column(conn, col["id"], new_type)
            await _apply_column_attrs(conn, col["id"], label, type, position, required)
            updated = await conn.fetchrow(
                "SELECT id, slug, label, type, position, required "
                "FROM dataset_column WHERE id = $1",
                col["id"],
            )
    assert updated is not None
    return dict(updated) | {"id": str(updated["id"])}


async def _retype_column(conn: asyncpg.Connection, column_id: uuid.UUID, new_type: str) -> None:
    """Re-coerce toutes les cellules de la colonne ; rejette (422) si une échoue."""
    cells = await conn.fetch(
        "SELECT row_ref, value FROM dataset_cell WHERE column_ref = $1", column_id
    )
    coerced: list[tuple[uuid.UUID, dict[str, object]]] = []
    faulty: list[str] = []
    for cell in cells:
        try:
            coerced.append((cell["row_ref"], coerce_cell(new_type, cell["value"])))  # type: ignore[arg-type]
        except ValueError:
            faulty.append(repr(cell["value"]))
    if faulty:
        raise HTTPException(
            status_code=422,
            detail=(
                f"retypage vers '{new_type}' impossible : "
                f"valeur(s) non convertible(s) : {', '.join(faulty)}"
            ),
        )
    for row_ref, shadow in coerced:
        await conn.execute(
            "UPDATE dataset_cell SET num_value = $1, date_value = $2, bool_value = $3 "
            "WHERE row_ref = $4 AND column_ref = $5",
            shadow["num_value"],
            shadow["date_value"],
            shadow["bool_value"],
            row_ref,
            column_id,
        )


async def _apply_column_attrs(
    conn: asyncpg.Connection,
    column_id: uuid.UUID,
    label: str | None,
    type: str | None,
    position: int | None,
    required: bool | None,
) -> None:
    sets: list[str] = []
    params: list[object] = []
    for field, val in (
        ("label", label),
        ("type", type),
        ("position", position),
        ("required", required),
    ):
        if val is not None:
            params.append(val)
            sets.append(f"{field} = ${len(params)}")
    if not sets:
        return
    params.append(column_id)
    await conn.execute(
        f"UPDATE dataset_column SET {', '.join(sets)} WHERE id = ${len(params)}",
        *params,
    )


async def delete_column(
    pool: asyncpg.Pool, ws_slug: str, dataset_id: uuid.UUID, column_slug: str
) -> dict[str, object]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug, allow_archived=False)
        await _require_dataset(conn, wk, dataset_id)
        deleted = await conn.fetchval(
            "DELETE FROM dataset_column WHERE dataset_ref = $1 AND slug = $2 RETURNING id",
            dataset_id,
            column_slug,
        )
    if deleted is None:
        raise HTTPException(
            status_code=404, detail=f"colonne '{column_slug}' introuvable dans ce dataset"
        )
    return {"deleted": True, "column_slug": column_slug}


async def add_row(
    pool: asyncpg.Pool,
    ws_slug: str,
    dataset_id: uuid.UUID,
    cells: dict[str, str],
    position: int | None = None,
) -> dict[str, object]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug, allow_archived=False)
        await _require_dataset(conn, wk, dataset_id)
        columns = await _columns_by_slug(conn, dataset_id)
        shadows = _coerce_cells(columns, cells)
        async with conn.transaction():
            if position is None:
                position = await conn.fetchval(
                    "SELECT coalesce(max(position) + 1, 0) FROM dataset_row WHERE dataset_ref = $1",
                    dataset_id,
                )
            row_id = await conn.fetchval(
                "INSERT INTO dataset_row (dataset_ref, position) VALUES ($1, $2) RETURNING id",
                dataset_id,
                position,
            )
            await _write_cells(conn, row_id, shadows)
    return {"row_id": str(row_id)}


async def update_row(
    pool: asyncpg.Pool,
    ws_slug: str,
    dataset_id: uuid.UUID,
    row_id: uuid.UUID,
    cells: dict[str, str],
) -> dict[str, object]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug, allow_archived=False)
        await _require_dataset(conn, wk, dataset_id)
        exists = await conn.fetchval(
            "SELECT 1 FROM dataset_row WHERE id = $1 AND dataset_ref = $2",
            row_id,
            dataset_id,
        )
        if exists is None:
            raise HTTPException(status_code=404, detail=f"ligne '{row_id}' introuvable")
        columns = await _columns_by_slug(conn, dataset_id)
        shadows = _coerce_cells(columns, cells)
        async with conn.transaction():
            await _write_cells(conn, row_id, shadows, upsert=True)
    return {"row_id": str(row_id), "updated": True}


async def delete_row(
    pool: asyncpg.Pool, ws_slug: str, dataset_id: uuid.UUID, row_id: uuid.UUID
) -> dict[str, object]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug, allow_archived=False)
        await _require_dataset(conn, wk, dataset_id)
        deleted = await conn.fetchval(
            "DELETE FROM dataset_row WHERE id = $1 AND dataset_ref = $2 RETURNING id",
            row_id,
            dataset_id,
        )
    if deleted is None:
        raise HTTPException(status_code=404, detail=f"ligne '{row_id}' introuvable")
    return {"deleted": True, "row_id": str(row_id)}


def _coerce_cells(
    columns: dict[str, asyncpg.Record], cells: dict[str, str]
) -> list[tuple[uuid.UUID, dict[str, object]]]:
    """Valide les colonnes et coerce chaque valeur ; (column_id, shadow) par cellule."""
    result: list[tuple[uuid.UUID, dict[str, object]]] = []
    for col_slug, raw in cells.items():
        col = _require_column(columns, col_slug)
        shadow = _coerce_or_422(col["type"], raw, col_slug)
        result.append((col["id"], shadow))
    return result


async def _write_cells(
    conn: asyncpg.Connection,
    row_id: uuid.UUID,
    shadows: list[tuple[uuid.UUID, dict[str, object]]],
    *,
    upsert: bool = False,
) -> None:
    for column_id, shadow in shadows:
        query = (
            "INSERT INTO dataset_cell "
            "(row_ref, column_ref, value, num_value, date_value, bool_value) "
            "VALUES ($1, $2, $3, $4, $5, $6)"
        )
        if upsert:
            query += (
                " ON CONFLICT (row_ref, column_ref) DO UPDATE SET "
                "value = EXCLUDED.value, num_value = EXCLUDED.num_value, "
                "date_value = EXCLUDED.date_value, bool_value = EXCLUDED.bool_value"
            )
        await conn.execute(
            query,
            row_id,
            column_id,
            shadow["value"],
            shadow["num_value"],
            shadow["date_value"],
            shadow["bool_value"],
        )

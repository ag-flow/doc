"""CRUD et résolution des vues sauvegardées (spec 37 — MVIEW)."""
from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
from fastapi import HTTPException
from pydantic import BaseModel, field_validator

from docflow.db.helpers import require_workspace, validate_slug
from docflow.views.filter_engine import FilterBuilder

# ── Schémas ───────────────────────────────────────────────────────────────────


class ViewCreate(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str
    layout: str
    filter: list[dict[str, Any]] = []
    sort: list[dict[str, Any]] = []
    group_by: str | None = None
    columns: list[str] = []
    bloc_ref: uuid.UUID | None = None
    shared: bool = False  # True → owner_ref = null

    @field_validator("slug")
    @classmethod
    def _slug_valid(cls, v: str) -> str:
        return validate_slug(v, "slug")

    @field_validator("layout")
    @classmethod
    def _layout_valid(cls, v: str) -> str:
        if v not in {"table", "board"}:
            raise ValueError("layout doit être 'table' ou 'board'")
        return v


class ViewUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = None
    layout: str | None = None
    filter: list[dict[str, Any]] | None = None
    sort: list[dict[str, Any]] | None = None
    group_by: str | None = None
    columns: list[str] | None = None
    shared: bool | None = None


class ViewOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    layout: str
    filter: list[dict[str, Any]]
    sort: list[dict[str, Any]]
    group_by: str | None
    columns: list[str]
    bloc_ref: uuid.UUID | None
    owner_ref: uuid.UUID | None
    created_at: str
    updated_at: str


class ViewResultRow(BaseModel):
    doc_id: uuid.UUID
    title: str
    type_slug: str | None
    bloc_ref: uuid.UUID | None


class ViewResults(BaseModel):
    rows: list[ViewResultRow]
    group_by_values: list[dict[str, Any]] = []  # allowed_values ordonnés pour board
    next_cursor: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_out(r: asyncpg.Record) -> ViewOut:
    return ViewOut(
        id=r["id"],
        slug=r["slug"],
        label=r["label"],
        layout=r["layout"],
        filter=json.loads(r["filter"]) if isinstance(r["filter"], str) else r["filter"],
        sort=json.loads(r["sort"]) if isinstance(r["sort"], str) else r["sort"],
        group_by=r["group_by"],
        columns=json.loads(r["columns"]) if isinstance(r["columns"], str) else r["columns"],
        bloc_ref=r["bloc_ref"],
        owner_ref=r["owner_ref"],
        created_at=r["created_at"].isoformat(),
        updated_at=r["updated_at"].isoformat(),
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def create_view(
    pool: asyncpg.Pool, ws_slug: str, caller_id: uuid.UUID, data: ViewCreate
) -> ViewOut:
    owner_ref = None if data.shared else caller_id
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO saved_view
                        (workspace_technical_key, bloc_ref, owner_ref, slug, label,
                         layout, filter, sort, group_by, columns)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING id, slug, label, layout, filter, sort, group_by,
                              columns, bloc_ref, owner_ref, created_at, updated_at
                    """,
                    wk,
                    data.bloc_ref,
                    owner_ref,
                    data.slug,
                    data.label,
                    data.layout,
                    json.dumps(data.filter),
                    json.dumps(data.sort),
                    data.group_by,
                    json.dumps(data.columns),
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"vue '{data.slug}' déjà existante dans ce workspace",
                ) from exc
    assert row is not None
    return _row_to_out(row)


async def list_views(
    pool: asyncpg.Pool, ws_slug: str, caller_id: uuid.UUID
) -> list[ViewOut]:
    """Retourne les vues partagées + les vues privées de l'appelant."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT id, slug, label, layout, filter, sort, group_by,
                   columns, bloc_ref, owner_ref, created_at, updated_at
            FROM saved_view
            WHERE workspace_technical_key = $1
              AND (owner_ref IS NULL OR owner_ref = $2)
            ORDER BY created_at
            """,
            wk,
            caller_id,
        )
    return [_row_to_out(r) for r in rows]


async def get_view(
    pool: asyncpg.Pool, ws_slug: str, slug: str, caller_id: uuid.UUID
) -> ViewOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            """
            SELECT id, slug, label, layout, filter, sort, group_by,
                   columns, bloc_ref, owner_ref, created_at, updated_at
            FROM saved_view
            WHERE workspace_technical_key = $1 AND slug = $2
              AND (owner_ref IS NULL OR owner_ref = $3)
            """,
            wk,
            slug,
            caller_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"vue '{slug}' introuvable")
    return _row_to_out(row)


async def update_view(
    pool: asyncpg.Pool, ws_slug: str, slug: str, caller_id: uuid.UUID, data: ViewUpdate
) -> ViewOut:
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        return await get_view(pool, ws_slug, slug, caller_id)

    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            row = await conn.fetchrow(
                "SELECT id, owner_ref FROM saved_view "
                "WHERE workspace_technical_key = $1 AND slug = $2 FOR UPDATE",
                wk,
                slug,
            )
            if row is None:
                raise HTTPException(status_code=404, detail=f"vue '{slug}' introuvable")
            # Seul l'auteur peut modifier une vue
            if row["owner_ref"] is not None and row["owner_ref"] != caller_id:
                raise HTTPException(status_code=403, detail="vous n'êtes pas l'auteur de cette vue")

            db_updates: dict[str, object] = {}
            for k, v in updates.items():
                if k == "shared":
                    db_updates["owner_ref"] = None if v else caller_id
                elif k in {"filter", "sort", "columns"}:
                    db_updates[k] = json.dumps(v)
                else:
                    db_updates[k] = v

            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(db_updates))
            updated = await conn.fetchrow(
                f"UPDATE saved_view SET {cols}, updated_at = now() WHERE id = $1 "
                "RETURNING id, slug, label, layout, filter, sort, group_by, "
                "columns, bloc_ref, owner_ref, created_at, updated_at",
                row["id"],
                *list(db_updates.values()),
            )
    assert updated is not None
    return _row_to_out(updated)


async def delete_view(
    pool: asyncpg.Pool, ws_slug: str, slug: str, caller_id: uuid.UUID
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            row = await conn.fetchrow(
                "SELECT id, owner_ref FROM saved_view "
                "WHERE workspace_technical_key = $1 AND slug = $2",
                wk,
                slug,
            )
            if row is None:
                raise HTTPException(status_code=404, detail=f"vue '{slug}' introuvable")
            if row["owner_ref"] is not None and row["owner_ref"] != caller_id:
                raise HTTPException(status_code=403, detail="vous n'êtes pas l'auteur de cette vue")
            await conn.execute("DELETE FROM saved_view WHERE id = $1", row["id"])


# ── Résolution de la vue ──────────────────────────────────────────────────────

async def resolve_view(
    pool: asyncpg.Pool,
    ws_slug: str,
    slug: str,
    caller_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 50,
) -> ViewResults:
    view = await get_view(pool, ws_slug, slug, caller_id)

    fb = FilterBuilder()
    for pred in view.filter:
        try:
            fb.add(pred)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Construire ORDER BY
    sort_parts: list[str] = []
    sort_params: list[Any] = []
    for s in view.sort:
        field = s.get("field", "")
        direction = "DESC" if str(s.get("dir", "asc")).lower() == "desc" else "ASC"
        if field == "@title":
            sort_parts.append(f"d.title {direction}")
        elif field == "@type":
            sort_parts.append(f"ft.slug {direction} NULLS LAST")
        elif not field.startswith("@"):
            n = len(fb.params) + len(sort_params) + 3
            sort_parts.append(
                f"(SELECT pvv_s.value FROM properties_values pv_s "
                f"JOIN properties_defs pd_s ON pd_s.id = pv_s.property_def_ref "
                f"JOIN properties_value_version pvv_s "
                f"ON pvv_s.property_value_ref = pv_s.id "
                f"AND pvv_s.version_number = pv_s.version "
                f"WHERE pv_s.document_ref = d.doc_technical_key "
                f"AND pd_s.slug = ${n}) {direction} NULLS LAST"
            )
            sort_params.append(field)

    order_by = "ORDER BY " + ", ".join(sort_parts) if sort_parts else "ORDER BY d.created_at"

    base_params: list[Any] = []
    async with pool.acquire() as conn:
        wk_row = await conn.fetchrow(
            "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
        )
        if wk_row is None:
            raise HTTPException(status_code=404, detail=f"workspace '{ws_slug}' introuvable")
        wk = wk_row["workspace_technical_key"]

    base_params = [wk, view.bloc_ref]  # $1 = ws, $2 = bloc_ref
    filter_sql = fb.where_clause()
    filter_params = fb.params

    # Décalage des $n du filtre et du sort
    # Les paramètres de base sont $1, $2 ; filtre commence à $3
    # Renuméroter les placeholders du filtre (ils commencent à $1 dans FilterBuilder)
    offset = 2  # $1 et $2 sont déjà pris
    for i, _p in enumerate(filter_params, start=1):
        filter_sql = filter_sql.replace(f"${i}", f"${i + offset}", 1)

    all_params: list[Any] = base_params + filter_params + sort_params

    bloc_clause = "AND ($2::uuid IS NULL OR d.data_block_ref = $2)"

    sql = f"""
        SELECT d.doc_technical_key AS doc_id,
               d.title,
               ft.slug             AS type_slug,
               d.data_block_ref    AS bloc_ref
        FROM document d
        LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
        WHERE d.workspace_technical_key = $1
          {bloc_clause}
          {filter_sql}
        {order_by}
        LIMIT ${len(all_params) + 1}
    """
    all_params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *all_params)

    result_rows = [
        ViewResultRow(
            doc_id=r["doc_id"],
            title=r["title"],
            type_slug=r["type_slug"],
            bloc_ref=r["bloc_ref"],
        )
        for r in rows
    ]

    # Board : charger les allowed_values ordonnées pour group_by
    group_by_values: list[dict[str, Any]] = []
    if view.layout == "board" and view.group_by:
        async with pool.acquire() as conn:
            av_rows = await conn.fetch(
                """
                SELECT pav.slug, pav.label, pav.position, pav.color
                FROM properties_allowed_values pav
                JOIN properties_defs pd ON pd.id = pav.property_def_ref
                JOIN functional_type ft ON ft.id = pd.functional_type_ref
                WHERE ft.workspace_technical_key = $1 AND pd.slug = $2
                ORDER BY pav.position, pav.created_at
                """,
                wk,
                view.group_by,
            )
            group_by_values = [dict(r) for r in av_rows]

    return ViewResults(rows=result_rows, group_by_values=group_by_values)

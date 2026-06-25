from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_prop_def, require_type, require_workspace
from docflow.schemas.properties import (
    AllowedValueCreate,
    AllowedValueOut,
    AllowedValueUpdate,
    PropertiesDefCreate,
    PropertiesDefOut,
    PropertiesDefUpdate,
)

# ── Properties defs ───────────────────────────────────────────────────────────

_SELECT_DEF = """
SELECT id, slug, label, type, default_value, required, created_at, updated_at
FROM properties_defs WHERE functional_type_ref = $1 AND slug = $2
"""
_SELECT_ALL_DEFS = """
SELECT id, slug, label, type, default_value, required, created_at, updated_at
FROM properties_defs WHERE functional_type_ref = $1 ORDER BY created_at
"""
_INSERT_DEF = """
INSERT INTO properties_defs
    (slug, label, functional_type_ref, type, default_value, required)
VALUES ($1, $2, $3, $4, $5, $6)
RETURNING id, slug, label, type, default_value, required, created_at, updated_at
"""
_UPDATE_DEF = (
    "UPDATE properties_defs SET {cols}, updated_at = now() WHERE id = $1 "
    "RETURNING id, slug, label, type, default_value, required, created_at, updated_at"
)

# ── Allowed values ────────────────────────────────────────────────────────────

_SELECT_VAL = """
SELECT id, slug, label, position, color, created_at
FROM properties_allowed_values WHERE property_def_ref = $1 AND slug = $2
"""
_SELECT_ALL_VALS = """
SELECT id, slug, label, position, color, created_at
FROM properties_allowed_values WHERE property_def_ref = $1 ORDER BY position, created_at
"""
_INSERT_VAL = """
INSERT INTO properties_allowed_values
    (property_def_ref, slug, label, position, color)
VALUES ($1, $2, $3, $4, $5)
RETURNING id, slug, label, position, color, created_at
"""
_UPDATE_VAL = (
    "UPDATE properties_allowed_values SET {cols} WHERE id = $1 "
    "RETURNING id, slug, label, position, color, created_at"
)
_SELECT_VAL_ID = (
    "SELECT id FROM properties_allowed_values "
    "WHERE property_def_ref = $1 AND slug = $2"
)


def _def_row(row: asyncpg.Record) -> PropertiesDefOut:
    return PropertiesDefOut(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        type=row["type"],
        default_value=row["default_value"],
        required=row["required"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _val_row(row: asyncpg.Record) -> AllowedValueOut:
    return AllowedValueOut(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        position=row["position"],
        color=row["color"],
        created_at=row["created_at"],
    )


async def _resolve_type_id(
    conn: asyncpg.Connection, ws_slug: str, type_slug: str
) -> uuid.UUID:
    wk = await require_workspace(conn, ws_slug)
    return await require_type(conn, wk, type_slug)


async def _resolve_prop_id_rl(
    conn: asyncpg.Connection, ws_slug: str, type_slug: str, prop_slug: str
) -> uuid.UUID:
    """Résout et valide que la propriété est de type restricted_list."""
    type_id = await _resolve_type_id(conn, ws_slug, type_slug)
    prop_id, prop_type = await require_prop_def(conn, type_id, prop_slug)
    if prop_type != "restricted_list":
        raise HTTPException(
            status_code=422,
            detail=(
                "les valeurs autorisées ne sont disponibles que "
                "pour les propriétés de type restricted_list"
            ),
        )
    return prop_id


async def list_defs(
    pool: asyncpg.Pool, ws_slug: str, type_slug: str
) -> list[PropertiesDefOut]:
    async with pool.acquire() as conn:
        type_id = await _resolve_type_id(conn, ws_slug, type_slug)
        rows = await conn.fetch(_SELECT_ALL_DEFS, type_id)
    return [_def_row(r) for r in rows]


async def get_def(
    pool: asyncpg.Pool, ws_slug: str, type_slug: str, prop_slug: str
) -> PropertiesDefOut:
    async with pool.acquire() as conn:
        type_id = await _resolve_type_id(conn, ws_slug, type_slug)
        row = await conn.fetchrow(_SELECT_DEF, type_id, prop_slug)
    if row is None:
        raise HTTPException(status_code=404, detail=f"propriété '{prop_slug}' introuvable")
    return _def_row(row)


async def create_def(
    pool: asyncpg.Pool, ws_slug: str, type_slug: str, data: PropertiesDefCreate
) -> PropertiesDefOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            type_id = await _resolve_type_id(conn, ws_slug, type_slug)
            try:
                row = await conn.fetchrow(
                    _INSERT_DEF,
                    data.slug, data.label, type_id, data.type, data.default_value, data.required,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"propriété '{data.slug}' déjà définie sur ce type",
                ) from exc
    assert row is not None
    return _def_row(row)


async def update_def(
    pool: asyncpg.Pool,
    ws_slug: str,
    type_slug: str,
    prop_slug: str,
    data: PropertiesDefUpdate,
) -> PropertiesDefOut:
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return await get_def(pool, ws_slug, type_slug, prop_slug)
    _ALLOWED = frozenset({"label", "default_value", "required"})
    for k in updates:
        if k not in _ALLOWED:
            raise ValueError(f"champ non modifiable : {k}")
    async with pool.acquire() as conn:
        async with conn.transaction():
            type_id = await _resolve_type_id(conn, ws_slug, type_slug)
            prop_id, _ = await require_prop_def(conn, type_id, prop_slug)
            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
            row = await conn.fetchrow(
                _UPDATE_DEF.format(cols=cols), prop_id, *list(updates.values())
            )
    assert row is not None
    return _def_row(row)


async def delete_def(
    pool: asyncpg.Pool, ws_slug: str, type_slug: str, prop_slug: str
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            type_id = await _resolve_type_id(conn, ws_slug, type_slug)
            prop_id, _ = await require_prop_def(conn, type_id, prop_slug)
            try:
                await conn.execute("DELETE FROM properties_defs WHERE id = $1", prop_id)
            except asyncpg.ForeignKeyViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="propriété utilisée par des valeurs existantes",
                ) from exc


async def list_allowed_values(
    pool: asyncpg.Pool, ws_slug: str, type_slug: str, prop_slug: str
) -> list[AllowedValueOut]:
    async with pool.acquire() as conn:
        prop_id = await _resolve_prop_id_rl(conn, ws_slug, type_slug, prop_slug)
        rows = await conn.fetch(_SELECT_ALL_VALS, prop_id)
    return [_val_row(r) for r in rows]


async def get_allowed_value(
    pool: asyncpg.Pool, ws_slug: str, type_slug: str, prop_slug: str, val_slug: str
) -> AllowedValueOut:
    async with pool.acquire() as conn:
        prop_id = await _resolve_prop_id_rl(conn, ws_slug, type_slug, prop_slug)
        row = await conn.fetchrow(_SELECT_VAL, prop_id, val_slug)
    if row is None:
        raise HTTPException(status_code=404, detail=f"valeur '{val_slug}' introuvable")
    return _val_row(row)


async def create_allowed_value(
    pool: asyncpg.Pool,
    ws_slug: str,
    type_slug: str,
    prop_slug: str,
    data: AllowedValueCreate,
) -> AllowedValueOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            prop_id = await _resolve_prop_id_rl(conn, ws_slug, type_slug, prop_slug)
            try:
                row = await conn.fetchrow(
                    _INSERT_VAL,
                    prop_id, data.slug, data.label, data.position, data.color,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"valeur '{data.slug}' déjà définie",
                ) from exc
    assert row is not None
    return _val_row(row)


async def update_allowed_value(
    pool: asyncpg.Pool,
    ws_slug: str,
    type_slug: str,
    prop_slug: str,
    val_slug: str,
    data: AllowedValueUpdate,
) -> AllowedValueOut:
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return await get_allowed_value(pool, ws_slug, type_slug, prop_slug, val_slug)
    _ALLOWED = frozenset({"label", "position", "color"})
    for k in updates:
        if k not in _ALLOWED:
            raise ValueError(f"champ non modifiable : {k}")
    async with pool.acquire() as conn:
        async with conn.transaction():
            prop_id = await _resolve_prop_id_rl(conn, ws_slug, type_slug, prop_slug)
            val_id: uuid.UUID | None = await conn.fetchval(
                _SELECT_VAL_ID, prop_id, val_slug
            )
            if val_id is None:
                raise HTTPException(status_code=404, detail=f"valeur '{val_slug}' introuvable")
            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
            row = await conn.fetchrow(
                _UPDATE_VAL.format(cols=cols), val_id, *list(updates.values())
            )
    assert row is not None
    return _val_row(row)


async def delete_allowed_value(
    pool: asyncpg.Pool, ws_slug: str, type_slug: str, prop_slug: str, val_slug: str
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            prop_id = await _resolve_prop_id_rl(conn, ws_slug, type_slug, prop_slug)
            val_id = await conn.fetchval(_SELECT_VAL_ID, prop_id, val_slug)
            if val_id is None:
                raise HTTPException(status_code=404, detail=f"valeur '{val_slug}' introuvable")
            try:
                await conn.execute(
                    "DELETE FROM properties_allowed_values WHERE id = $1", val_id
                )
            except asyncpg.ForeignKeyViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="valeur utilisée par des documents existants",
                ) from exc

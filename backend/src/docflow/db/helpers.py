from __future__ import annotations

import re
import uuid

import asyncpg
from fastapi import HTTPException

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def validate_slug(value: str, field: str = "slug") -> str:
    """Valide qu'une valeur respecte le format slug. Lève ValueError pour pydantic."""
    if not value or not _SLUG_RE.match(value) or len(value) > 100:
        raise ValueError(
            f"{field} invalide : {value!r} (attendu: ^[a-z0-9][a-z0-9_-]*, longueur 1–100)"
        )
    return value


async def require_workspace(
    conn: asyncpg.Connection, ws_slug: str, *, allow_archived: bool = True
) -> uuid.UUID:
    """Résout un slug de workspace → workspace_technical_key, ou lève 404.

    Par défaut `allow_archived=True` : les lectures restent autorisées sur un
    workspace archivé. Les écritures passent `allow_archived=False` : un
    workspace archivé est alors en lecture seule et l'écriture est refusée (409).
    """
    row = await conn.fetchrow(
        "SELECT workspace_technical_key, archived_at FROM workspace WHERE slug = $1",
        ws_slug,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"workspace '{ws_slug}' introuvable")
    if not allow_archived and row["archived_at"] is not None:
        raise HTTPException(
            status_code=409,
            detail=f"workspace '{ws_slug}' est archivé (lecture seule)",
        )
    wk: uuid.UUID = row["workspace_technical_key"]
    return wk


async def require_type(conn: asyncpg.Connection, wk: uuid.UUID, type_slug: str) -> uuid.UUID:
    """Résout un slug de type → functional_type.id, ou lève 404."""
    type_id: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        type_slug,
    )
    if type_id is None:
        raise HTTPException(status_code=404, detail=f"type '{type_slug}' introuvable")
    return type_id


async def require_prop_def(
    conn: asyncpg.Connection, type_id: uuid.UUID, prop_slug: str
) -> tuple[uuid.UUID, str]:
    """Résout un slug de propriété → (id, type). Lève 404 si absent."""
    row = await conn.fetchrow(
        "SELECT id, type FROM properties_defs WHERE functional_type_ref = $1 AND slug = $2",
        type_id,
        prop_slug,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"propriété '{prop_slug}' introuvable")
    return row["id"], row["type"]

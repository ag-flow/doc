"""Lectures asyncpg de la phase DB du git_sync.

Ces coroutines s'exécutent dans le loop principal (le pool asyncpg est lié à
son event loop) ; elles produisent des structures pures consommées ensuite par
la phase git bloquante.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from docflow.backup.git_files import SLUG_SAFE


async def fetch_doc(conn: asyncpg.Connection, doc_id: uuid.UUID) -> dict[str, Any] | None:
    """Retourne les données brutes d'un document avec son contenu et ses propriétés."""
    row = await conn.fetchrow(
        """
        SELECT d.doc_technical_key AS id, d.slug, d.title, d.updated_at,
               d.parent AS parent_id,
               d.workspace_technical_key AS workspace_id,
               ft.slug AS functional_type_slug,
               dv.content
        FROM document d
        LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
        LEFT JOIN document_version dv
               ON dv.document_ref = d.doc_technical_key
              AND dv.version_number = d.version
        WHERE d.doc_technical_key = $1
        """,
        doc_id,
    )
    if row is None:
        return None
    doc = dict(row)

    prop_rows = await conn.fetch(
        """
        SELECT pd.slug AS prop_slug, pd.type AS prop_type,
               pvv.value, pav.slug AS allowed_value_slug
        FROM properties_values pv
        JOIN properties_defs pd ON pd.id = pv.property_def_ref
        JOIN properties_value_version pvv
               ON pvv.property_value_ref = pv.id
              AND pvv.version_number = pv.version
        LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
        WHERE pv.document_ref = $1
        ORDER BY pd.slug
        """,
        doc_id,
    )
    doc["properties"] = {
        r["prop_slug"]: r["value"] if r["value"] is not None else r["allowed_value_slug"]
        for r in prop_rows
    }
    return doc


async def build_path(
    conn: asyncpg.Connection,
    doc_id: uuid.UUID,
    workspace_slug: str,
) -> list[str] | None:
    """Remonte l'arborescence et retourne la liste de slugs [racine, ..., doc].
    Retourne None si un ancêtre n'a pas de slug (skip ce document)."""
    parts: list[str] = []
    current_id: uuid.UUID | None = doc_id
    while current_id is not None:
        row = await conn.fetchrow(
            "SELECT slug, parent FROM document WHERE doc_technical_key = $1",
            current_id,
        )
        if row is None:
            return None
        slug = row["slug"]
        if not slug or not SLUG_SAFE.match(slug):
            return None  # document sans slug → skip
        parts.insert(0, slug)
        current_id = row["parent"]
    # Préfixe workspace
    parts.insert(0, workspace_slug)
    return parts


async def fetch_ws_documents(
    conn: asyncpg.Connection, workspace_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Retourne (id, slug, parent) de tous les documents du workspace."""
    rows = await conn.fetch(
        """
        SELECT doc_technical_key AS id, slug, parent
        FROM document WHERE workspace_technical_key = $1
        """,
        workspace_id,
    )
    return [dict(r) for r in rows]

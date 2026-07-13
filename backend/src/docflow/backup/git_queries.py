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


async def resolve_block_scope(conn: asyncpg.Connection, block_id: uuid.UUID) -> set[uuid.UUID]:
    """Retourne l'ensemble {block_id} ∪ descendance (CTE récursive sur data_block.parent).

    Même pattern que blocks/service.py:count_block_dependents.
    """
    rows = await conn.fetch(
        """
        WITH RECURSIVE subtree AS (
            SELECT id FROM data_block WHERE id = $1
            UNION ALL
            SELECT b.id FROM data_block b JOIN subtree s ON b.parent = s.id
        )
        SELECT id FROM subtree
        """,
        block_id,
    )
    return {r["id"] for r in rows}


async def fetch_doc(conn: asyncpg.Connection, doc_id: uuid.UUID) -> dict[str, Any] | None:
    """Retourne les données brutes d'un document avec son contenu et ses propriétés."""
    row = await conn.fetchrow(
        """
        SELECT d.doc_technical_key AS id, d.slug, d.title, d.updated_at,
               d.parent AS parent_id,
               d.workspace_technical_key AS workspace_id,
               d.data_block_ref AS data_block_id,
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
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
    block_scope: set[uuid.UUID] | None = None,
) -> list[dict[str, Any]]:
    """Retourne (id, slug, parent) des documents du workspace.

    `block_scope` restreint aux documents dont le bloc appartient à cet
    ensemble (résolu via `resolve_block_scope`) — None = tout le workspace.
    """
    rows = await conn.fetch(
        """
        SELECT doc_technical_key AS id, slug, parent
        FROM document
        WHERE workspace_technical_key = $1
          AND ($2::uuid[] IS NULL OR data_block_ref = ANY($2::uuid[]))
        """,
        workspace_id,
        list(block_scope) if block_scope is not None else None,
    )
    return [dict(r) for r in rows]


async def collect_full_export(
    conn: asyncpg.Connection,
    *,
    workspace_technical_key: uuid.UUID | None,
    workspace_slug: str | None,
    block_scope: set[uuid.UUID] | None,
) -> tuple[list[tuple[list[str], dict[str, Any]]], dict[str, set[str]]]:
    """Collecte l'export initial complet du périmètre (premier run d'un job).

    Le journal des changements ne couvre pas les documents antérieurs à sa
    mise en place : on exporte donc tout le périmètre. Retourne
    (to_write, reconcile) au même format que la collecte incrémentale.
    """
    from docflow.backup.git_files import expected_file_paths

    if workspace_technical_key is not None:
        ws_slug = workspace_slug or await conn.fetchval(
            "SELECT slug FROM workspace WHERE workspace_technical_key = $1",
            workspace_technical_key,
        )
        ws_list: list[tuple[uuid.UUID, str]] = (
            [(workspace_technical_key, ws_slug)] if ws_slug else []
        )
    else:
        ws_list = [
            (r["workspace_technical_key"], r["slug"])
            for r in await conn.fetch("SELECT workspace_technical_key, slug FROM workspace")
        ]

    to_write: list[tuple[list[str], dict[str, Any]]] = []
    reconcile: dict[str, set[str]] = {}
    for ws_id, ws_slug in ws_list:
        docs = await fetch_ws_documents(conn, ws_id, block_scope=block_scope)
        reconcile[ws_slug] = expected_file_paths(ws_slug, docs)
        for d in docs:
            doc = await fetch_doc(conn, d["id"])
            if doc is None:
                continue
            path_parts = await build_path(conn, d["id"], ws_slug)
            if path_parts is None:
                continue
            to_write.append((path_parts, doc))
    return to_write, reconcile


async def collect_incremental(
    conn: asyncpg.Connection,
    *,
    workspace_technical_key: uuid.UUID | None,
    workspace_slug: str | None,
    last_change_seq: int,
    block_scope: set[uuid.UUID] | None,
) -> tuple[int, list[tuple[list[str], dict[str, Any]]], dict[str, set[str]]] | None:
    """Collecte les documents modifiés depuis `last_change_seq` (journal).

    Retourne (nouveau curseur, to_write, reconcile), ou None si aucun
    changement. La réconciliation ne couvre que les workspaces présents dans
    le batch : un workspace sans changement n'est jamais touché.
    """
    from docflow.backup.git_files import expected_file_paths

    where_ws = "AND workspace_technical_key = $2" if workspace_technical_key else ""
    params: list[Any] = [last_change_seq]
    if workspace_technical_key:
        params.append(workspace_technical_key)
    change_rows = await conn.fetch(
        f"""
        SELECT seq, document_ref, nature, workspace_technical_key AS ws_id
        FROM document_change_log
        WHERE seq > $1 {where_ws}
        ORDER BY seq
        """,
        *params,
    )
    if not change_rows:
        return None

    to_write: list[tuple[list[str], dict[str, Any]]] = []
    for row in change_rows:
        if row["nature"] in ("C", "U", "P"):
            ws_slug = workspace_slug or await conn.fetchval(
                "SELECT slug FROM workspace WHERE workspace_technical_key = $1",
                row["ws_id"],
            )
            if not ws_slug:
                continue
            doc = await fetch_doc(conn, row["document_ref"])
            if doc is None:
                continue  # supprimé entre-temps — géré par la réconciliation
            if block_scope is not None and doc["data_block_id"] not in block_scope:
                continue  # hors du périmètre bloc de ce job
            path_parts = await build_path(conn, row["document_ref"], ws_slug)
            if path_parts is None:
                continue  # document sans slug valide — même règle qu'à l'export complet
            to_write.append((path_parts, doc))

    reconcile: dict[str, set[str]] = {}
    for ws_id in {row["ws_id"] for row in change_rows}:
        ws_slug = workspace_slug or await conn.fetchval(
            "SELECT slug FROM workspace WHERE workspace_technical_key = $1",
            ws_id,
        )
        if not ws_slug:
            continue  # workspace introuvable → ne rien purger
        docs = await fetch_ws_documents(conn, ws_id, block_scope=block_scope)
        reconcile[ws_slug] = expected_file_paths(ws_slug, docs)

    return change_rows[-1]["seq"], to_write, reconcile

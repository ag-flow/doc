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
        ) CYCLE id SET is_cycle USING path
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
    block_parts: list[str] | None = None,
) -> list[str] | None:
    """Remonte l'arborescence et retourne [workspace, *blocs, ..., doc].

    `block_parts` : chaîne de slugs du bloc du document (cf. fetch_block_paths).
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
    # Préfixes blocs puis workspace
    for part in reversed(block_parts or []):
        parts.insert(0, part)
    parts.insert(0, workspace_slug)
    return parts


async def fetch_ws_documents(
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
    block_scope: set[uuid.UUID] | None = None,
) -> list[dict[str, Any]]:
    """Retourne (id, slug, parent, data_block_ref) des documents du workspace.

    `block_scope` restreint aux documents dont le bloc appartient à cet
    ensemble (résolu via `resolve_block_scope`) — None = tout le workspace.
    """
    rows = await conn.fetch(
        """
        SELECT doc_technical_key AS id, slug, parent, data_block_ref
        FROM document
        WHERE workspace_technical_key = $1
          AND ($2::uuid[] IS NULL OR data_block_ref = ANY($2::uuid[]))
        """,
        workspace_id,
        list(block_scope) if block_scope is not None else None,
    )
    return [dict(r) for r in rows]


async def fetch_block_paths(
    conn: asyncpg.Connection, workspace_id: uuid.UUID
) -> dict[uuid.UUID, list[str] | None]:
    """Chaîne de slugs [racine, ..., bloc] pour chaque bloc du workspace.

    None si un slug de la chaîne est absent/invalide (documents alors sautés,
    même règle que pour un document sans slug)."""
    rows = await conn.fetch(
        "SELECT id, slug, parent FROM data_block WHERE workspace_technical_key = $1",
        workspace_id,
    )
    by_id = {r["id"]: r for r in rows}
    chains: dict[uuid.UUID, list[str] | None] = {}

    def _chain(block_id: uuid.UUID, seen: set[uuid.UUID]) -> list[str] | None:
        if block_id in chains:
            return chains[block_id]
        row = by_id.get(block_id)
        if row is None or block_id in seen:
            return None  # parent hors workspace ou cycle
        seen.add(block_id)
        slug = row["slug"]
        if not slug or not SLUG_SAFE.match(slug):
            chains[block_id] = None
            return None
        if row["parent"] is None:
            chains[block_id] = [slug]
        else:
            parent_chain = _chain(row["parent"], seen)
            chains[block_id] = None if parent_chain is None else [*parent_chain, slug]
        return chains[block_id]

    for bid in by_id:
        _chain(bid, set())
    return chains


async def collect_block_meta_files(
    conn: asyncpg.Connection,
    workspace_slug: str,
    block_paths: dict[uuid.UUID, list[str] | None],
    block_scope: set[uuid.UUID] | None,
) -> tuple[list[tuple[list[str], str]], set[str]]:
    """(fichiers `_block.yaml` à écrire, chemins attendus correspondants).

    Un fichier par bloc du périmètre : métadonnées + template du type racine
    (cf. type_export). Les chemins attendus alimentent la réconciliation.
    """
    from docflow.backup.type_export import BLOCK_META_FILENAME, block_meta_yaml

    files: list[tuple[list[str], str]] = []
    expected: set[str] = set()
    for block_id, parts in block_paths.items():
        if parts is None:
            continue
        if block_scope is not None and block_id not in block_scope:
            continue
        content = await block_meta_yaml(conn, block_id)
        if content is None:
            continue
        path_parts = [workspace_slug, *parts, BLOCK_META_FILENAME]
        files.append((path_parts, content))
        expected.add("/".join(path_parts))
    return files, expected


async def collect_full_export(
    conn: asyncpg.Connection,
    *,
    workspace_technical_key: uuid.UUID | None,
    workspace_slug: str | None,
    block_scope: set[uuid.UUID] | None,
) -> tuple[
    list[tuple[list[str], dict[str, Any]]],
    dict[str, set[str]],
    list[tuple[list[str], str]],
]:
    """Collecte l'export initial complet du périmètre (premier run d'un job).

    Le journal des changements ne couvre pas les documents antérieurs à sa
    mise en place : on exporte donc tout le périmètre. Retourne
    (to_write, reconcile, extra_files) — extra_files = les `_block.yaml`.
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
    extra_files: list[tuple[list[str], str]] = []
    for ws_id, ws_slug in ws_list:
        block_paths = await fetch_block_paths(conn, ws_id)
        docs = await fetch_ws_documents(conn, ws_id, block_scope=block_scope)
        for d in docs:
            d["block_parts"] = block_paths.get(d["data_block_ref"])
        meta_files, meta_expected = await collect_block_meta_files(
            conn, ws_slug, block_paths, block_scope
        )
        extra_files.extend(meta_files)
        reconcile[ws_slug] = expected_file_paths(ws_slug, docs) | meta_expected
        for d in docs:
            doc = await fetch_doc(conn, d["id"])
            if doc is None:
                continue
            path_parts = await build_path(conn, d["id"], ws_slug, d["block_parts"])
            if path_parts is None:
                continue
            to_write.append((path_parts, doc))
    return to_write, reconcile, extra_files


async def collect_incremental(
    conn: asyncpg.Connection,
    *,
    workspace_technical_key: uuid.UUID | None,
    workspace_slug: str | None,
    last_change_seq: int,
    block_scope: set[uuid.UUID] | None,
) -> (
    tuple[
        int,
        list[tuple[list[str], dict[str, Any]]],
        dict[str, set[str]],
        list[tuple[list[str], str]],
    ]
    | None
):
    """Collecte les documents modifiés depuis `last_change_seq` (journal).

    Retourne (nouveau curseur, to_write, reconcile, extra_files `_block.yaml`),
    ou None si aucun changement. La réconciliation ne couvre que les
    workspaces présents dans le batch : un workspace sans changement n'est
    jamais touché. Les `_block.yaml` des workspaces du batch sont régénérés à
    chaque run (un changement de structure seul ne déclenche pas de run :
    il est repris au prochain changement de document).
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

    block_paths_by_ws: dict[uuid.UUID, dict[uuid.UUID, list[str] | None]] = {}

    async def _ws_block_paths(ws_id: uuid.UUID) -> dict[uuid.UUID, list[str] | None]:
        if ws_id not in block_paths_by_ws:
            block_paths_by_ws[ws_id] = await fetch_block_paths(conn, ws_id)
        return block_paths_by_ws[ws_id]

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
            block_parts = (await _ws_block_paths(row["ws_id"])).get(doc["data_block_id"])
            if block_parts is None:
                continue  # chaîne de blocs invalide — même règle qu'un slug manquant
            path_parts = await build_path(conn, row["document_ref"], ws_slug, block_parts)
            if path_parts is None:
                continue  # document sans slug valide — même règle qu'à l'export complet
            to_write.append((path_parts, doc))

    reconcile: dict[str, set[str]] = {}
    extra_files: list[tuple[list[str], str]] = []
    for ws_id in {row["ws_id"] for row in change_rows}:
        ws_slug = workspace_slug or await conn.fetchval(
            "SELECT slug FROM workspace WHERE workspace_technical_key = $1",
            ws_id,
        )
        if not ws_slug:
            continue  # workspace introuvable → ne rien purger
        block_paths = await _ws_block_paths(ws_id)
        docs = await fetch_ws_documents(conn, ws_id, block_scope=block_scope)
        for d in docs:
            d["block_parts"] = block_paths.get(d["data_block_ref"])
        meta_files, meta_expected = await collect_block_meta_files(
            conn, ws_slug, block_paths, block_scope
        )
        extra_files.extend(meta_files)
        reconcile[ws_slug] = expected_file_paths(ws_slug, docs) | meta_expected

    return change_rows[-1]["seq"], to_write, reconcile, extra_files

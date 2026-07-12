"""Tests du périmètre bloc + descendance (resolve_block_scope, fetch_ws_documents).

Ces primitives portent le filtrage consommé par run_git_sync pour restreindre
la synchronisation git d'un backup_job à un bloc et sa descendance, plutôt
qu'à tout le workspace (comportement par défaut, inchangé).
"""

from __future__ import annotations

import uuid

import asyncpg

from docflow.backup.git_queries import fetch_ws_documents, resolve_block_scope
from docflow.documents import service as doc_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

# Le fixture `test_workspace` (conftest.py) crée le workspace de slug "test-ws".
_WS = "test-ws"


async def _setup_blocks(pool: asyncpg.Pool) -> dict[str, uuid.UUID]:
    """Arborescence de blocs root -> child -> grandchild, + un bloc "other" isolé.

    Un document racine par bloc — vérifie que le filtrage suit la hiérarchie
    des BLOCS (data_block.parent), pas celle des documents.
    """
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="task", label="Task"))
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug=$1", _WS
    )
    ft: uuid.UUID = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='task'", wk
    )

    async def _block(slug: str, parent: uuid.UUID | None) -> uuid.UUID:
        block_id: uuid.UUID = await pool.fetchval(
            "INSERT INTO data_block (slug, label, functional_type_ref, "
            "workspace_technical_key, parent) VALUES ($1, $1, $2, $3, $4) RETURNING id",
            slug,
            ft,
            wk,
            parent,
        )
        return block_id

    root = await _block("root", None)
    child = await _block("child", root)
    grandchild = await _block("grandchild", child)
    other = await _block("other", None)

    async def _doc(slug: str, block_id: uuid.UUID) -> None:
        await doc_svc.create_document(
            pool,
            _WS,
            DocumentCreate(title=slug, slug=slug, block_id=block_id, functional_type_slug="task"),
        )

    await _doc("doc-root", root)
    await _doc("doc-child", child)
    await _doc("doc-grandchild", grandchild)
    await _doc("doc-other", other)

    return {"wk": wk, "root": root, "child": child, "grandchild": grandchild, "other": other}


async def test_resolve_block_scope_includes_descendants(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    blocks = await _setup_blocks(db_pool)
    async with db_pool.acquire() as conn:
        scope = await resolve_block_scope(conn, blocks["root"])
    assert scope == {blocks["root"], blocks["child"], blocks["grandchild"]}
    assert blocks["other"] not in scope


async def test_resolve_block_scope_leaf_is_singleton(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    blocks = await _setup_blocks(db_pool)
    async with db_pool.acquire() as conn:
        scope = await resolve_block_scope(conn, blocks["grandchild"])
    assert scope == {blocks["grandchild"]}


async def test_fetch_ws_documents_filters_by_block_scope(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    blocks = await _setup_blocks(db_pool)
    async with db_pool.acquire() as conn:
        scope = await resolve_block_scope(conn, blocks["root"])
        docs = await fetch_ws_documents(conn, blocks["wk"], block_scope=scope)
    slugs = {d["slug"] for d in docs}
    assert slugs == {"doc-root", "doc-child", "doc-grandchild"}


async def test_fetch_ws_documents_without_scope_returns_all(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    blocks = await _setup_blocks(db_pool)
    async with db_pool.acquire() as conn:
        docs = await fetch_ws_documents(conn, blocks["wk"])
    slugs = {d["slug"] for d in docs}
    assert slugs == {"doc-root", "doc-child", "doc-grandchild", "doc-other"}

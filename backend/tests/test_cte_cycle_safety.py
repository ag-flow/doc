"""Cycle-safety des CTE récursives (niveau 2 de la défense anti-cycle).

Un cycle injecté directement en SQL (contournant la validation applicative)
ne doit plus faire boucler aucune CTE récursive : chaque fonction concernée
doit TERMINER avec un résultat borné, sous asyncio.timeout(5), au lieu de
pendre et bloquer une connexion du pool.
"""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.artifacts.service import collect_subtree_artifacts
from docflow.backup.git_queries import resolve_block_scope
from docflow.backup.type_export import _fetch_type_subtree
from docflow.blocks import introspection
from docflow.blocks import service as block_svc
from docflow.documents import block_tree
from docflow.documents import service as doc_svc
from docflow.documents.block_query import _resolve_prop_types
from docflow.errors import DependentsConflictError
from docflow.schemas.document import DocumentCreate, DocumentUpdate
from docflow.schemas.types import FunctionalTypeCreate, FunctionalTypeUpdate
from docflow.types import service as type_svc

_WS = "test-ws"

_TIMEOUT = 5


async def _make_doc_cycle(
    db_pool: asyncpg.Pool, block_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """A→B→A : B enfant de A par l'API, puis A reparenté sous B en SQL brut."""
    doc_a = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Cycle A", block_id=block_id)
    )
    doc_b = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Cycle B", parent_id=doc_a.doc_technical_key, block_id=block_id),
    )
    await db_pool.execute(
        "UPDATE document SET parent = $2 WHERE doc_technical_key = $1",
        doc_a.doc_technical_key,
        doc_b.doc_technical_key,
    )
    return doc_a.doc_technical_key, doc_b.doc_technical_key


async def _make_type_cycle(db_pool: asyncpg.Pool, wk: uuid.UUID) -> uuid.UUID:
    """ct1→ct2→ct1 : ct2 enfant de ct1 par l'API, puis ct1 sous ct2 en SQL brut."""
    ct1 = await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="ct1", label="Cycle T1")
    )
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="ct2", label="Cycle T2", parent_slug="ct1")
    )
    await db_pool.execute(
        "UPDATE functional_type SET parent = "
        "(SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'ct2') "
        "WHERE workspace_technical_key = $1 AND slug = 'ct1'",
        wk,
    )
    return ct1.id


async def _make_block_cycle(
    db_pool: asyncpg.Pool, wk: uuid.UUID, type_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """bc1→bc2→bc1 sur data_block.parent, injecté en SQL brut."""
    bc1: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ('bc1', 'BC1', $1, $2) RETURNING id",
        type_id,
        wk,
    )
    bc2: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO data_block "
        "(slug, label, functional_type_ref, workspace_technical_key, parent) "
        "VALUES ('bc2', 'BC2', $1, $2, $3) RETURNING id",
        type_id,
        wk,
        bc1,
    )
    await db_pool.execute("UPDATE data_block SET parent = $2 WHERE id = $1", bc1, bc2)
    return bc1, bc2


# ── Hiérarchie documents ──────────────────────────────────────────────────────


async def test_count_descendants_terminates_on_doc_cycle(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    a, _ = await _make_doc_cycle(db_pool, test_block["id"])
    async with asyncio.timeout(_TIMEOUT):
        with pytest.raises(DependentsConflictError):
            await doc_svc.delete_document(db_pool, _WS, a, confirm=False)


async def test_set_exposed_terminates_on_doc_cycle(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    a, _ = await _make_doc_cycle(db_pool, test_block["id"])
    async with asyncio.timeout(_TIMEOUT):
        doc = await doc_svc.set_document_exposed(db_pool, _WS, a, True)
    assert doc.exposed is True


async def test_collect_subtree_artifacts_terminates_on_doc_cycle(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    a, _ = await _make_doc_cycle(db_pool, test_block["id"])
    async with asyncio.timeout(_TIMEOUT):
        async with db_pool.acquire() as conn:
            artifacts = await collect_subtree_artifacts(conn, a)
    assert artifacts == []


async def test_block_tree_terminates_with_doc_cycle_in_block(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """Le cycle (aucun de ses membres n'est racine) reste hors de l'arbre rendu."""
    root = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Racine saine", block_id=test_block["id"])
    )
    await _make_doc_cycle(db_pool, test_block["id"])
    async with asyncio.timeout(_TIMEOUT):
        page = await block_tree.list_block_tree(db_pool, _WS, test_block["slug"])
    assert [r.id for r in page.roots] == [str(root.doc_technical_key)]


async def test_reparent_under_preexisting_doc_cycle_terminates(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """La validation elle-même ne doit pas boucler si la chaîne d'ancêtres est cyclique."""
    a, _ = await _make_doc_cycle(db_pool, test_block["id"])
    doc_c = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc C", block_id=test_block["id"])
    )
    async with asyncio.timeout(_TIMEOUT):
        with pytest.raises(HTTPException) as exc:
            await doc_svc.update_document(
                db_pool, _WS, doc_c.doc_technical_key, DocumentUpdate(parent_id=a)
            )
    assert exc.value.status_code == 422


# ── Hiérarchie types fonctionnels ─────────────────────────────────────────────


async def test_count_type_dependents_terminates_on_type_cycle(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block
) -> None:
    await _make_type_cycle(db_pool, test_workspace["workspace_technical_key"])
    await make_block(_WS, "ct1", "ct-block")
    async with asyncio.timeout(_TIMEOUT):
        with pytest.raises(DependentsConflictError):
            await type_svc.delete_type(db_pool, _WS, "ct1", confirm=False)


async def test_list_block_properties_terminates_on_type_cycle(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block
) -> None:
    await _make_type_cycle(db_pool, test_workspace["workspace_technical_key"])
    await make_block(_WS, "ct1", "ct-block")
    async with asyncio.timeout(_TIMEOUT):
        out = await introspection.list_block_properties(db_pool, _WS, "ct-block")
    assert sorted(t.functional_type_slug for t in out.types) == ["ct1", "ct2"]


async def test_resolve_prop_types_terminates_on_type_cycle(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block
) -> None:
    wk: uuid.UUID = test_workspace["workspace_technical_key"]
    await _make_type_cycle(db_pool, wk)
    await make_block(_WS, "ct1", "ct-block")
    async with asyncio.timeout(_TIMEOUT):
        async with db_pool.acquire() as conn:
            with pytest.raises(HTTPException) as exc:
                await _resolve_prop_types(conn, wk, "ct-block", ["inconnue"])
    assert exc.value.status_code == 422


async def test_type_export_subtree_terminates_on_type_cycle(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    ct1_id = await _make_type_cycle(db_pool, test_workspace["workspace_technical_key"])
    async with asyncio.timeout(_TIMEOUT):
        async with db_pool.acquire() as conn:
            subtree = await _fetch_type_subtree(conn, ct1_id)
    assert sorted(t["slug"] for t in subtree) == ["ct1", "ct2"]


async def test_reparent_type_under_preexisting_cycle_terminates(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _make_type_cycle(db_pool, test_workspace["workspace_technical_key"])
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="ct3", label="Cycle T3"))
    async with asyncio.timeout(_TIMEOUT):
        with pytest.raises(HTTPException) as exc:
            await type_svc.update_type(db_pool, _WS, "ct3", FunctionalTypeUpdate(parent_slug="ct1"))
    assert exc.value.status_code == 422


# ── Hiérarchie blocs ──────────────────────────────────────────────────────────


async def test_count_block_dependents_terminates_on_block_cycle(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    await _make_block_cycle(
        db_pool, test_workspace["workspace_technical_key"], test_block["type_id"]
    )
    async with asyncio.timeout(_TIMEOUT):
        counts = await block_svc.count_block_dependents(db_pool, _WS, "bc1")
    assert counts == {"child_blocks": 1, "documents": 0}


async def test_resolve_block_scope_terminates_on_block_cycle(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    bc1, bc2 = await _make_block_cycle(
        db_pool, test_workspace["workspace_technical_key"], test_block["type_id"]
    )
    async with asyncio.timeout(_TIMEOUT):
        async with db_pool.acquire() as conn:
            scope = await resolve_block_scope(conn, bc1)
    assert scope == {bc1, bc2}

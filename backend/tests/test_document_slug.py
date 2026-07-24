"""ATDD — Slug d'instance unique par fratrie (déduplication déterministe).

Given/When/Then :
- deux enfants de même titre sous le même parent → suffixe incrémental,
- trois enfants de même kind (même titre) → base, -2, -3,
- ré-import par external_id → idempotent, slugs stables,
- slug explicite en collision → 409 (intention appelant préservée).
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.documents.slug import document_base_slug
from docflow.documents.sync import sync_child_documents
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import PropertiesDefCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc


async def _setup(pool: asyncpg.Pool) -> tuple[str, uuid.UUID, uuid.UUID]:
    """Workspace + type capture/capture_item (external_id) + bloc + parent."""
    ws = f"slug-{uuid.uuid4().hex[:8]}"
    await pool.execute("INSERT INTO workspace (slug, label) VALUES ($1, $2)", ws, "Slug ATDD")
    wk = await pool.fetchval("SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws)
    await type_svc.create_type(pool, ws, FunctionalTypeCreate(slug="capture", label="Capture"))
    await type_svc.create_type(
        pool, ws, FunctionalTypeCreate(slug="capture_item", label="Item", parent_slug="capture")
    )
    parent_type_id = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'capture'", wk
    )
    await prop_svc.create_def(
        pool, ws, "capture_item",
        PropertiesDefCreate(slug="external_id", label="External ID", type="text"),
    )
    block_id = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ('captures', 'Captures', $1, $2) RETURNING id",
        parent_type_id, wk,
    )
    parent = await doc_svc.create_document(
        pool, ws, DocumentCreate(title="Parent", functional_type_slug="capture", block_id=block_id)
    )
    return ws, block_id, parent.doc_technical_key


async def _child(pool: asyncpg.Pool, ws: str, block: uuid.UUID, parent: uuid.UUID, title: str):
    return await doc_svc.create_document(
        pool, ws,
        DocumentCreate(
            title=title, functional_type_slug="capture_item", block_id=block, parent_id=parent
        ),
    )


# ── Given/When/Then ───────────────────────────────────────────────────────────


async def test_two_children_same_title_get_incremental_slug(db_pool: asyncpg.Pool) -> None:
    ws, block, parent = await _setup(db_pool)
    c1 = await _child(db_pool, ws, block, parent, "Compte rendu")
    c2 = await _child(db_pool, ws, block, parent, "Compte rendu")
    assert c1.slug == "compte-rendu"
    assert c2.slug == "compte-rendu-2"


async def test_three_same_kind_same_title_sequence(db_pool: asyncpg.Pool) -> None:
    ws, block, parent = await _setup(db_pool)
    slugs = [(await _child(db_pool, ws, block, parent, "Action")).slug for _ in range(3)]
    assert slugs == ["action", "action-2", "action-3"]


async def test_reimport_by_external_id_idempotent_and_slugs_stable(db_pool: asyncpg.Pool) -> None:
    ws, block, parent = await _setup(db_pool)
    items = [
        {"external_id": "x1", "title": "Note", "contenu": "c1"},
        {"external_id": "x2", "title": "Note", "contenu": "c2"},  # même titre
    ]
    r1 = await sync_child_documents(db_pool, ws, parent, "capture_item", items, False)
    assert r1["counts"]["created"] == 2  # type: ignore[index]

    async def _slugs(ids: list[str]) -> set[str]:
        out = set()
        for i in ids:
            out.add(await db_pool.fetchval(
                "SELECT slug FROM document WHERE doc_technical_key = $1", uuid.UUID(i)
            ))
        return out

    created_ids: list[str] = r1["created"]  # type: ignore[assignment]
    assert await _slugs(created_ids) == {"note", "note-2"}

    # Rejeu à l'identique → aucune création, slugs inchangés (matché par external_id).
    r2 = await sync_child_documents(db_pool, ws, parent, "capture_item", items, False)
    assert r2["counts"]["created"] == 0  # type: ignore[index]
    assert await _slugs(created_ids) == {"note", "note-2"}


async def test_explicit_slug_collision_returns_409(db_pool: asyncpg.Pool) -> None:
    ws, block, parent = await _setup(db_pool)
    await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(
            title="A", slug="resume", functional_type_slug="capture_item",
            block_id=block, parent_id=parent,
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.create_document(
            db_pool, ws,
            DocumentCreate(
                title="B", slug="resume", functional_type_slug="capture_item",
                block_id=block, parent_id=parent,
            ),
        )
    assert exc.value.status_code == 409


def test_base_slug_derivation() -> None:
    assert document_base_slug("Compte Rendu !") == "compte-rendu"
    assert document_base_slug("Réunion client") == "reunion-client"
    assert document_base_slug("   ") == "doc"      # vide → fallback
    assert document_base_slug("A") == "doc"        # trop court → fallback
    assert len(document_base_slug("x" * 200)) <= 76

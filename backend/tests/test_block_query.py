"""Tests épic MCP docflow — listing paginé des objets d'un bloc + query filtrée paginée."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.documents.block_query import list_block_objects, query_documents
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import AllowedValueCreate, PropertiesDefCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _setup(pool: asyncpg.Pool, statuts: list[str]) -> uuid.UUID:
    """Bloc 'board' typé epic + statut restricted_list ; un epic par valeur de `statuts`.

    Retourne le block_id. Les titres sont ordonnés pour un test de pagination stable.
    """
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
    )
    epic_id: uuid.UUID = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'epic'", wk
    )
    block_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        "board",
        "Board",
        epic_id,
        wk,
    )
    await prop_svc.create_def(
        pool, _WS, "epic",
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list"),
    )
    for slug, label, pos in [("todo", "À faire", 0), ("done", "Done", 1)]:
        await prop_svc.create_allowed_value(
            pool, _WS, "epic", "statut", AllowedValueCreate(slug=slug, label=label, position=pos)
        )
    for i, st in enumerate(statuts):
        await doc_svc.create_document(
            pool,
            _WS,
            DocumentCreate(
                title=f"Epic {i:02d}",
                slug=f"epic-{i:02d}",
                block_id=block_id,
                functional_type_slug="epic",
                properties={"statut": st},
            ),
        )
    return block_id


# ── list_block_objects ────────────────────────────────────────────────────────


async def test_list_objects_carries_property_values(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _setup(db_pool, ["todo", "done"])
    page = await list_block_objects(db_pool, _WS, "board", page=1, page_size=50)

    assert page.total == 2
    assert page.has_next is False
    first = page.objects[0]
    assert first.title == "Epic 00"
    statut = next(p for p in first.properties if p.prop_slug == "statut")
    assert statut.allowed_value_slug == "todo"
    assert statut.allowed_value_label == "À faire"


async def test_list_objects_pagination(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool, ["todo"] * 5)
    p1 = await list_block_objects(db_pool, _WS, "board", page=1, page_size=2)
    assert p1.total == 5
    assert len(p1.objects) == 2
    assert p1.has_next is True
    assert [o.title for o in p1.objects] == ["Epic 00", "Epic 01"]

    p3 = await list_block_objects(db_pool, _WS, "board", page=3, page_size=2)
    assert len(p3.objects) == 1
    assert p3.has_next is False
    assert p3.objects[0].title == "Epic 04"


async def test_list_objects_page_size_bounds(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _setup(db_pool, ["todo"])
    with pytest.raises(HTTPException) as exc:
        await list_block_objects(db_pool, _WS, "board", page=1, page_size=9999)
    assert exc.value.status_code == 422


# ── query_documents ───────────────────────────────────────────────────────────


async def test_query_filters_by_restricted_value(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _setup(db_pool, ["todo", "done", "todo", "done", "todo"])
    page = await query_documents(db_pool, _WS, "board", {"statut": "done"}, page=1, page_size=50)

    assert page.total == 2
    for obj in page.objects:
        statut = next(p for p in obj.properties if p.prop_slug == "statut")
        assert statut.allowed_value_slug == "done"


async def test_query_pagination_on_filtered_set(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _setup(db_pool, ["todo", "done", "todo", "done", "todo", "done"])
    p1 = await query_documents(db_pool, _WS, "board", {"statut": "todo"}, page=1, page_size=2)
    assert p1.total == 3
    assert len(p1.objects) == 2
    assert p1.has_next is True


async def test_query_empty_filter_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _setup(db_pool, ["todo"])
    with pytest.raises(HTTPException) as exc:
        await query_documents(db_pool, _WS, "board", {}, page=1, page_size=50)
    assert exc.value.status_code == 422


async def test_query_via_mcp_tool(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    import json

    from docflow.mcp.server import _TOOLS, _call_tool, configure

    assert any(t.name == "query_documents" for t in _TOOLS)
    assert any(t.name == "list_block_objects" for t in _TOOLS)
    await _setup(db_pool, ["todo", "done", "todo"])
    configure(db_pool)
    result = await _call_tool(
        "query_documents",
        {"workspace_slug": _WS, "block_slug": "board", "filters": {"statut": "todo"}},
    )
    payload = json.loads(result[0].text)
    assert payload["total"] == 2
    assert payload["page"] == 1

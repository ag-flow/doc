from __future__ import annotations

import json

import asyncpg
import pytest

from docflow.mcp.server import (
    _TOOLS,
    _call_tool,
    _create_document,
    _get_document,
    _list_documents,
    _list_types,
    _list_workspaces,
    configure,
)


async def test_list_tools_returns_all_tools(db_pool: asyncpg.Pool) -> None:
    """list_tools retourne bien les 8 outils définis."""
    tool_names = {t.name for t in _TOOLS}
    assert "list_workspaces" in tool_names
    assert "list_types" in tool_names
    assert "list_documents" in tool_names
    assert "get_document" in tool_names
    assert "create_document" in tool_names
    assert "update_document" in tool_names
    assert "list_property_values" in tool_names
    assert "set_property_value" in tool_names
    assert len(_TOOLS) == 8


async def test_configure_sets_pool(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    from docflow.mcp.server import _pool
    assert _pool is db_pool


async def test_list_workspaces_empty(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    result = await _list_workspaces(db_pool)
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert isinstance(data, list)


async def test_list_workspaces_with_data(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    await db_pool.execute(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        "mcp-test-ws", "MCP Test WS",
    )
    result = await _list_workspaces(db_pool)
    data = json.loads(result[0].text)
    slugs = [d["slug"] for d in data]
    assert "mcp-test-ws" in slugs


async def test_list_types_unknown_workspace(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    with pytest.raises(ValueError, match="introuvable"):
        await _list_types(db_pool, "unknown-ws")


async def test_list_documents_unknown_workspace(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    with pytest.raises(ValueError, match="introuvable"):
        await _list_documents(db_pool, "not-exist")


async def test_get_document_not_found(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    import uuid
    await db_pool.execute(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        "ws-doc-test", "WS Doc Test",
    )
    result = await _get_document(db_pool, "ws-doc-test", str(uuid.uuid4()))
    data = json.loads(result[0].text)
    assert "error" in data


async def test_call_tool_unknown_name(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    result = await _call_tool("nonexistent_tool", {})
    data = json.loads(result[0].text)
    assert "error" in data


async def test_create_and_get_document_via_mcp(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    await db_pool.execute(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        "mcp-crud-ws", "MCP CRUD WS",
    )
    result = await _create_document(
        db_pool,
        {
            "workspace_slug": "mcp-crud-ws",
            "title": "Doc créé via MCP",
            "contenu": "# Hello MCP",
        },
    )
    created = json.loads(result[0].text)
    assert created["created"] is True
    doc_id = created["id"]

    get_result = await _get_document(db_pool, "mcp-crud-ws", doc_id)
    doc = json.loads(get_result[0].text)
    assert doc["title"] == "Doc créé via MCP"
    assert doc["contenu"] == "# Hello MCP"

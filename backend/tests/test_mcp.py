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
    """list_tools retourne bien les 25 outils définis (liste exhaustive : test_mcp_tools.py)."""
    tool_names = {t.name for t in _TOOLS}
    assert "list_workspaces" in tool_names
    assert "list_types" in tool_names
    assert "list_documents" in tool_names
    assert "get_document" in tool_names
    assert "create_document" in tool_names
    assert "update_document" in tool_names
    assert "list_property_values" in tool_names
    assert "set_property_value" in tool_names
    assert "list_blocks" in tool_names
    assert "delete_block" in tool_names
    assert "create_artifact" in tool_names
    assert "get_artifact" in tool_names
    assert "get_artifact_link" in tool_names
    assert "list_block_properties" in tool_names
    assert "list_block_objects" in tool_names
    assert "query_documents" in tool_names
    assert "list_block_tree" in tool_names
    assert "sync_child_documents" in tool_names
    assert len(_TOOLS) == 30


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
        "mcp-test-ws",
        "MCP Test WS",
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
        "ws-doc-test",
        "WS Doc Test",
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
    wk: object = await db_pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) "
        "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug "
        "RETURNING workspace_technical_key",
        "mcp-crud-ws",
        "MCP CRUD WS",
    )
    root_type_id = await db_pool.fetchval(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ($1, $2, $3) RETURNING id",
        "mcp-root",
        "MCP Root",
        wk,
    )
    await db_pool.execute(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4)",
        "mcp-block",
        "MCP Block",
        root_type_id,
        wk,
    )
    result = await _create_document(
        db_pool,
        {
            "workspace_slug": "mcp-crud-ws",
            "block_slug": "mcp-block",
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

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
    """list_tools retourne bien les outils définis (liste exhaustive : test_mcp_tools.py)."""
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
    assert "get_artifact_data" in tool_names
    assert "list_block_properties" in tool_names
    assert "list_block_objects" in tool_names
    assert "query_documents" in tool_names
    assert "list_block_tree" in tool_names
    assert "sync_child_documents" in tool_names
    assert "find_by_dedup_key" in tool_names
    assert "set_dedup_key" in tool_names
    assert "list_workspace_members" in tool_names
    assert "add_workspace_member" in tool_names
    assert "remove_workspace_member" in tool_names
    assert "find_referencing_documents" in tool_names
    assert "search_documents" in tool_names
    for _t in (
        "create_dataset",
        "list_datasets",
        "get_dataset",
        "add_dataset_column",
        "update_dataset_column",
        "delete_dataset_column",
        "add_dataset_row",
        "update_dataset_row",
        "delete_dataset_row",
        "query_dataset",
        "import_dataset_csv",
        "export_dataset_csv",
    ):
        assert _t in tool_names
    assert "list_artifacts" in tool_names
    assert "create_upload" in tool_names
    assert "update_artifact" in tool_names
    assert "patch_artifact" in tool_names
    assert "get_preview_link" in tool_names
    assert len(_TOOLS) == 57


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


def test_finalize_marks_error_result_but_not_success() -> None:
    """Une erreur métier ({"error": ...}) → CallToolResult(isError=True) ; jamais
    ok:true/200 pour un échec. Un succès reste une liste de contenu inchangée."""
    from docflow.mcp.server import CallToolResult, _finalize_tool_result, _text

    ok = _text({"id": "abc", "url": "/x"})
    assert _finalize_tool_result(ok) is ok

    finalized = _finalize_tool_result(_text({"error": "propriété inconnue (I-2)"}))
    assert isinstance(finalized, CallToolResult)
    assert finalized.isError is True
    assert json.loads(finalized.content[0].text)["error"] == "propriété inconnue (I-2)"


async def test_call_tool_unknown_name(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    result = await _call_tool("nonexistent_tool", {})
    # Une erreur métier porte isError=True (CallToolResult) — jamais un succès.
    assert result.isError is True
    data = json.loads(result.content[0].text)
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


async def test_create_document_unknown_property_is_error_via_call_tool(
    db_pool: asyncpg.Pool,
) -> None:
    """Cas ag.flow : create_document avec une propriété que le type ne déclare pas.
    Un refus métier DOIT porter isError=True (jamais ok:true/200 pour la passerelle)."""
    from docflow.mcp.server import CallToolResult

    configure(db_pool)
    wk = await db_pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) "
        "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug "
        "RETURNING workspace_technical_key",
        "mcp-err-ws",
        "MCP Err WS",
    )
    ft = await db_pool.fetchval(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING RETURNING id",
        "capture",
        "Capture",
        wk,
    ) or await db_pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'capture'",
        wk,
    )
    await db_pool.execute(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
        "captures",
        "Captures",
        ft,
        wk,
    )

    # Passage par _call_tool (le point exact que voit la passerelle MCP).
    result = await _call_tool(
        "create_document",
        {
            "workspace_slug": "mcp-err-ws",
            "block_slug": "captures",
            "title": "Capture",
            "functional_type_slug": "capture",
            "properties": {"ingested_at": "2026-07-30"},  # non déclarée sur le type
        },
    )
    assert isinstance(result, CallToolResult)
    assert result.isError is True
    payload = json.loads(result.content[0].text)
    assert "ingested_at" in payload["error"]


async def test_search_documents_mcp_cross_workspace(db_pool: asyncpg.Pool) -> None:
    """Le tool MCP search_documents cherche en plein-texte, borné aux droits de
    l'identité, et renvoie le nom du workspace."""
    import uuid

    from docflow.mcp.server import _search_documents
    from docflow.mcp.session import McpSession, reset_current_session, set_current_session
    from docflow.schemas.auth import AuthUser

    wk = await db_pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ('mcp-search-ws', 'Recherche WS') "
        "ON CONFLICT (slug) DO UPDATE SET label = EXCLUDED.label RETURNING workspace_technical_key",
    )
    ft = await db_pool.fetchval(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ('page', 'Page', $1) ON CONFLICT DO NOTHING RETURNING id",
        wk,
    ) or await db_pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug='page'", wk
    )
    blk = await db_pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ('blk', 'Bloc', $1, $2) ON CONFLICT DO NOTHING RETURNING id",
        ft,
        wk,
    ) or await db_pool.fetchval(
        "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug='blk'", wk
    )
    doc_id = await db_pool.fetchval(
        "INSERT INTO document (title, functional_type_ref, data_block_ref, "
        "workspace_technical_key, version) VALUES ('Divers', $1, $2, $3, 1) "
        "RETURNING doc_technical_key",
        ft,
        blk,
        wk,
    )
    await db_pool.execute(
        "INSERT INTO document_version (document_ref, version_number, title, content) "
        "VALUES ($1, 1, 'Divers', 'mot-cle-unique-xyz dans le corps')",
        doc_id,
    )

    user = AuthUser(
        id=uuid.uuid4(), email="s@t.local", label="S", is_admin=True, validated=True, disabled=False
    )
    token = set_current_session(McpSession(user=user))
    try:
        out = json.loads((await _search_documents(db_pool, {"q": "mot-cle-unique-xyz"}))[0].text)
        hit = next(h for h in out if h["workspace_slug"] == "mcp-search-ws")
        assert hit["workspace_label"] == "Recherche WS"
        assert hit["url"] == f"/api/workspaces/mcp-search-ws/documents/{hit['id']}"
        assert hit["app_url"] == f"/ws/mcp-search-ws/blocs/blk/documents/{hit['id']}"
        assert hit["version"] == 1
        assert "slug" in hit
    finally:
        reset_current_session(token)
        await db_pool.execute("DELETE FROM workspace WHERE slug = 'mcp-search-ws'")

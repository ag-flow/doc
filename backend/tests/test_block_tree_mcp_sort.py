"""Le tri serveur de `list_block_tree` est exposé sur la surface MCP.

Le moteur et l'API REST savent trier depuis l'origine (`sort` / `dir` côté REST) ;
la surface MCP ne le déclarait pas, donc aucun agent ne pouvait s'en servir.
Fichier à part : `test_block_tree.py` est à 299 lignes, au plafond du dépôt.

Nommage retenu : `sort_key` / `sort_dir`, et NON `sort` / `dir` comme en REST.
`query_documents` expose déjà un `sort` qui est une LISTE de `{key, dir}` ; un
paramètre `sort` qui serait une chaîne sur un outil et un tableau sur l'autre est
exactement le piège de vocabulaire qui fait mésappeler une surface.
"""

from __future__ import annotations

import json
import uuid

import asyncpg

from docflow.documents import service as doc_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _setup_roots(pool: asyncpg.Pool) -> None:
    """Bloc 'tree' avec trois racines de titres ordonnables : A, B, C."""
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="task", label="Task"))
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug=$1", _WS
    )
    task_ft: uuid.UUID = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='task'", wk
    )
    block_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO data_block (slug,label,functional_type_ref,workspace_technical_key) "
        "VALUES ('tree','Tree',$1,$2) RETURNING id",
        task_ft,
        wk,
    )
    for title, slug in [("A", "doc-a"), ("B", "doc-b"), ("C", "doc-c")]:
        await doc_svc.create_document(
            pool,
            _WS,
            DocumentCreate(title=title, slug=slug, block_id=block_id, functional_type_slug="task"),
        )


def test_mcp_tool_declares_the_sort_parameters() -> None:
    """Un paramètre non déclaré au schéma n'existe pas pour l'agent."""
    from docflow.mcp.server import _TOOLS

    tool = next(t for t in _TOOLS if t.name == "list_block_tree")
    props = tool.inputSchema["properties"]

    assert "sort_key" in props
    assert "sort_dir" in props


async def test_mcp_sort_dir_desc_reverses_roots(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Le tri demandé par MCP est réellement appliqué, pas ignoré."""
    from docflow.mcp.server import _call_tool, configure

    await _setup_roots(db_pool)
    configure(db_pool)

    result = await _call_tool(
        "list_block_tree",
        {"workspace_slug": _WS, "block_slug": "tree", "sort_dir": "desc"},
    )
    payload = json.loads(result[0].text)

    assert [r["title"] for r in payload["roots"]] == ["C", "B", "A"]


async def test_mcp_invalid_sort_key_is_refused(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """Une clé de tri inconnue est REFUSÉE, et le message nomme les clés valides.

    Sans cette garde, deux issues également mauvaises : un 500 (le moteur indexe
    une whitelist et lève `KeyError`), ou un tri silencieusement ignoré — l'agent
    croirait trier et lirait un ordre arbitraire.
    """
    from mcp.types import CallToolResult

    from docflow.mcp.server import _call_tool, configure

    await _setup_roots(db_pool)
    configure(db_pool)

    result = await _call_tool(
        "list_block_tree",
        {"workspace_slug": _WS, "block_slug": "tree", "sort_key": "titre"},
    )

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    text = result.content[0].text  # type: ignore[union-attr]
    assert "sort_key" in text
    assert "title" in text and "updated_at" in text

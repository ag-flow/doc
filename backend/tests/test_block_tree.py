"""Mode browse arbre : list_block_tree (racines paginées + sous-arbres + valeurs).

Pagination sur les RACINES ; chaque racine porte son sous-arbre complet (CTE
récursive) et les valeurs de propriétés de chaque nœud. Couvre : assemblage de
l'arbre, pagination sur les racines uniquement, ordre, bornes, 404, dispatch MCP.
"""

from __future__ import annotations

import json
import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.documents.block_tree import TREE_MAX_PAGE_SIZE, list_block_tree
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import PropertiesDefCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _setup(pool: asyncpg.Pool) -> uuid.UUID:
    """Bloc 'tree' : 3 niveaux de types (task ⊃ subtask ⊃ leaf), 5 racines.

    R1 porte un sous-arbre à deux niveaux (C1 → G1) ; R2..R5 sont des racines
    feuilles. Une propriété text 'note' par type pour vérifier le portage des
    valeurs sur chaque nœud.
    """
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="task", label="Task"))
    await type_svc.create_type(
        pool, _WS, FunctionalTypeCreate(slug="subtask", label="Subtask", parent_slug="task")
    )
    await type_svc.create_type(
        pool, _WS, FunctionalTypeCreate(slug="leaf", label="Leaf", parent_slug="subtask")
    )
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
    for tslug in ("task", "subtask", "leaf"):
        await prop_svc.create_def(
            pool, _WS, tslug, PropertiesDefCreate(slug="note", label="Note", type="text")
        )

    async def _mk(title: str, slug: str, tslug: str, parent: uuid.UUID | None) -> uuid.UUID:
        doc = await doc_svc.create_document(
            pool,
            _WS,
            DocumentCreate(
                title=title,
                slug=slug,
                block_id=block_id,
                functional_type_slug=tslug,
                parent_id=parent,
                properties={"note": f"note-{slug}"},
            ),
        )
        return doc.doc_technical_key

    r1 = await _mk("R1", "r1", "task", None)
    c1 = await _mk("C1", "c1", "subtask", r1)
    await _mk("G1", "g1", "leaf", c1)
    for slug in ("r2", "r3", "r4", "r5"):
        await _mk(slug.upper(), slug, "task", None)
    return block_id


# ── Assemblage de l'arbre ─────────────────────────────────────────────────────


async def test_subtree_assembly_and_values(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    page = await list_block_tree(db_pool, _WS, "tree", page=1, page_size=100)
    by_title = {n.title: n for n in page.roots}
    r1 = by_title["R1"]
    # R1 porte son sous-arbre récursif : R1 → C1 → G1.
    assert [c.title for c in r1.children] == ["C1"]
    c1 = r1.children[0]
    assert [g.title for g in c1.children] == ["G1"]
    g1 = c1.children[0]
    # Chaque nœud porte ses valeurs de propriétés et son parent_id.
    assert g1.parent_id == c1.id
    assert c1.parent_id == r1.id
    assert r1.parent_id is None
    notes = {v.prop_slug: v.value for v in g1.properties}
    assert notes.get("note") == "note-g1"
    assert g1.functional_type_slug == "leaf"


async def test_pagination_counts_roots_only(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    p1 = await list_block_tree(db_pool, _WS, "tree", page=1, page_size=2)
    # 5 racines ; page_size compte les racines, pas les enfants.
    assert p1.total == 5
    assert p1.has_next is True
    assert [n.title for n in p1.roots] == ["R1", "R2"]
    # La racine paginée conserve son sous-arbre complet malgré page_size=2.
    assert p1.roots[0].children[0].title == "C1"

    p3 = await list_block_tree(db_pool, _WS, "tree", page=3, page_size=2)
    assert [n.title for n in p3.roots] == ["R5"]
    assert p3.has_next is False


async def test_roots_ordered_by_title(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    page = await list_block_tree(db_pool, _WS, "tree", page=1, page_size=100)
    assert [n.title for n in page.roots] == ["R1", "R2", "R3", "R4", "R5"]


# ── Bornes & erreurs ──────────────────────────────────────────────────────────


async def test_page_size_capped_at_max(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    with pytest.raises(HTTPException) as exc:
        await list_block_tree(db_pool, _WS, "tree", page=1, page_size=TREE_MAX_PAGE_SIZE + 1)
    assert exc.value.status_code == 422


async def test_unknown_block_404(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    with pytest.raises(HTTPException) as exc:
        await list_block_tree(db_pool, _WS, "nope", page=1, page_size=50)
    assert exc.value.status_code == 404


async def test_empty_block_no_roots(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="task", label="Task"))
    wk: uuid.UUID = await db_pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug=$1", _WS
    )
    task_ft: uuid.UUID = await db_pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='task'", wk
    )
    await db_pool.execute(
        "INSERT INTO data_block (slug,label,functional_type_ref,workspace_technical_key) "
        "VALUES ('empty','Empty',$1,$2)",
        task_ft,
        wk,
    )
    page = await list_block_tree(db_pool, _WS, "empty", page=1, page_size=50)
    assert page.total == 0
    assert page.roots == []
    assert page.has_next is False


# ── Surface REST (end-to-end HTTP) ────────────────────────────────────────────


async def test_rest_tree_endpoint(
    db_pool: asyncpg.Pool,
    clean_admin_users: None,
    test_workspace: dict,
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
) -> None:
    from fastapi.testclient import TestClient

    from docflow.app import app

    await _setup(db_pool)
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", "test_jwt_secret_for_m2")
    with TestClient(app) as client:
        setup = client.post(
            "/api/setup/init-admin",
            json={"username": "boot", "email": "boot@example.com", "password": "boot_pw_123"},
        )
        assert setup.status_code == 201, setup.text
        login = client.post(
            "/api/auth/login", json={"email": "boot@example.com", "password": "boot_pw_123"}
        )
        hdrs = {"Authorization": f"Bearer {login.json()['access_token']}"}
        resp = client.get(
            f"/api/workspaces/{_WS}/blocks/tree/tree",
            headers=hdrs,
            params={"page": 1, "page_size": 100},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 5
    r1 = next(n for n in body["roots"] if n["title"] == "R1")
    assert r1["children"][0]["children"][0]["title"] == "G1"


# ── Dispatch MCP ──────────────────────────────────────────────────────────────


async def test_mcp_list_block_tree(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    from docflow.mcp.server import _call_tool, configure

    await _setup(db_pool)
    configure(db_pool)
    result = await _call_tool(
        "list_block_tree",
        {"workspace_slug": _WS, "block_slug": "tree", "page": 1, "page_size": 100},
    )
    data = json.loads(result[0].text)
    assert data["total"] == 5
    r1 = next(n for n in data["roots"] if n["title"] == "R1")
    assert r1["children"][0]["title"] == "C1"
    assert r1["children"][0]["children"][0]["title"] == "G1"

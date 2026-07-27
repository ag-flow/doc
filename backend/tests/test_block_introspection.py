"""Tests épic MCP docflow — introspection du schéma de propriétés d'un bloc (sans doc_id)."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.blocks.introspection import list_block_properties
from docflow.properties import service as prop_svc
from docflow.schemas.properties import (
    AllowedValueCreate,
    PropertiesDefCreate,
    PropertiesDefUpdate,
)
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _setup(pool: asyncpg.Pool) -> None:
    """epic ⊃ feature ; bloc 'board' typé epic ; statut sur epic (défaut) et feature."""
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await type_svc.create_type(
        pool, _WS, FunctionalTypeCreate(slug="feature", label="Feature", parent_slug="epic")
    )
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
    )
    epic_id: uuid.UUID = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'epic'", wk
    )
    await pool.execute(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4)",
        "board",
        "Board",
        epic_id,
        wk,
    )
    # statut sur epic (restricted_list, défaut a_cadrer)
    await prop_svc.create_def(
        pool,
        _WS,
        "epic",
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list"),
    )
    for slug, label, pos in [("a_cadrer", "À cadrer", 0), ("done", "Done", 1)]:
        await prop_svc.create_allowed_value(
            pool, _WS, "epic", "statut", AllowedValueCreate(slug=slug, label=label, position=pos)
        )
    await prop_svc.update_def(
        pool, _WS, "epic", "statut", PropertiesDefUpdate(default_value="a_cadrer")
    )
    # budget (int, required) sur epic pour couvrir un type scalaire
    await prop_svc.create_def(
        pool,
        _WS,
        "epic",
        PropertiesDefCreate(slug="budget", label="Budget", type="int", required=True),
    )
    # statut sur feature (vocabulaire distinct)
    await prop_svc.create_def(
        pool,
        _WS,
        "feature",
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list"),
    )
    await prop_svc.create_allowed_value(
        pool,
        _WS,
        "feature",
        "statut",
        AllowedValueCreate(slug="pret_pour_dev", label="Prêt pour dev", position=0),
    )


async def test_introspect_returns_root_type_schema(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _setup(db_pool)
    out = await list_block_properties(db_pool, _WS, "board")

    assert out.block_slug == "board"
    assert out.root_type_slug == "epic"

    root = next(t for t in out.types if t.is_block_root)
    assert root.functional_type_slug == "epic"
    statut = next(p for p in root.properties if p.prop_slug == "statut")
    assert statut.type == "restricted_list"
    assert statut.default_value == "a_cadrer"
    assert [v.slug for v in statut.allowed_values or []] == ["a_cadrer", "done"]
    # un scalaire required n'a pas de valeurs autorisées
    budget = next(p for p in root.properties if p.prop_slug == "budget")
    assert budget.required is True
    assert budget.allowed_values is None


async def test_introspect_covers_descendant_types(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Le schéma couvre les types imbriqués (feature), pas seulement la racine."""
    await _setup(db_pool)
    out = await list_block_properties(db_pool, _WS, "board")

    slugs = {t.functional_type_slug for t in out.types}
    assert {"epic", "feature"} <= slugs

    feature = next(t for t in out.types if t.functional_type_slug == "feature")
    assert feature.is_block_root is False
    f_statut = next(p for p in feature.properties if p.prop_slug == "statut")
    assert [v.slug for v in f_statut.allowed_values or []] == ["pret_pour_dev"]


async def test_introspect_unknown_block_404(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    with pytest.raises(HTTPException) as exc:
        await list_block_properties(db_pool, _WS, "nope")
    assert exc.value.status_code == 404


async def test_introspect_via_mcp_tool(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """La primitive est exposée et dispatchée par le serveur MCP."""
    import json

    from docflow.mcp.server import _TOOLS, _call_tool, configure

    assert any(t.name == "list_block_properties" for t in _TOOLS)
    await _setup(db_pool)
    configure(db_pool)
    result = await _call_tool(
        "list_block_properties", {"workspace_slug": _WS, "block_slug": "board"}
    )
    payload = json.loads(result[0].text)
    assert payload["root_type_slug"] == "epic"
    root = next(t for t in payload["types"] if t["is_block_root"])
    statut = next(p for p in root["properties"] if p["prop_slug"] == "statut")
    assert statut["default_value"] == "a_cadrer"
    assert [v["slug"] for v in statut["allowed_values"]] == ["a_cadrer", "done"]

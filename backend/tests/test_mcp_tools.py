"""Campagne de tests complète des 13 outils MCP + flag is_admin sur les profils API.

Chaque test appelle les handlers directement (pas via SSE) pour isoler la logique.
Couverture : chemin nominal, erreur métier, idempotence, guard admin.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest

from docflow.mcp.server import (
    _TOOLS,
    _call_tool,
    _create_block,
    _create_document,
    _create_workspace,
    _get_document,
    _get_property_value,
    _import_template,
    _list_documents,
    _list_property_values,
    _list_templates,
    _list_types,
    _list_workspaces,
    _set_property_value,
    _update_document,
    configure,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json(result: list) -> object:
    return json.loads(result[0].text)


# ---------------------------------------------------------------------------
# Fixture : workspace + type + bloc + document + propriété text
# ---------------------------------------------------------------------------


@pytest.fixture()
async def mcp_ws(db_pool: asyncpg.Pool) -> AsyncIterator[dict[str, object]]:
    """Workspace complet pour les tests MCP : type, bloc, document, propriété."""
    configure(db_pool)

    # Cleanup préventif au cas où un test précédent aurait planté sans teardown
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "mcp-camp-ws")

    row = await db_pool.fetchrow(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) "
        "RETURNING workspace_technical_key, slug",
        "mcp-camp-ws",
        "MCP Campaign WS",
    )
    assert row is not None
    wk: uuid.UUID = row["workspace_technical_key"]

    type_row = await db_pool.fetchrow(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ($1, $2, $3) RETURNING id, slug",
        "epic",
        "Epic",
        wk,
    )
    assert type_row is not None
    type_id: uuid.UUID = type_row["id"]

    await db_pool.execute(
        "INSERT INTO properties_defs (slug, label, type, functional_type_ref) "
        "VALUES ($1, $2, $3, $4)",
        "priority",
        "Priorité",
        "text",
        type_id,
    )

    from docflow.blocks import service as block_svc
    from docflow.schemas.block import DataBlockCreate

    bloc = await block_svc.create_block(
        db_pool,
        "mcp-camp-ws",
        DataBlockCreate(slug="epics", label="Epics", functional_type_slug="epic"),
    )

    doc_result = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": "mcp-camp-ws",
                "block_slug": "epics",
                "title": "Epic A",
                "contenu": "# Epic A",
                "functional_type_slug": "epic",
            },
        )
    )
    assert doc_result["created"] is True  # type: ignore[index]

    try:
        yield {
            "wk": wk,
            "ws_slug": "mcp-camp-ws",
            "type_slug": "epic",
            "type_id": type_id,
            "block_slug": bloc.slug,
            "doc_id": str(doc_result["id"]),
            "prop_slug": "priority",
        }
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "mcp-camp-ws")


# ---------------------------------------------------------------------------
# 1. Inventaire des outils
# ---------------------------------------------------------------------------


async def test_tools_count(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    names = {t.name for t in _TOOLS}
    expected = {
        "list_workspaces",
        "list_types",
        "list_documents",
        "get_document",
        "create_document",
        "update_document",
        "list_property_values",
        "get_property_value",
        "set_property_value",
        "list_templates",
        "create_workspace",
        "import_template",
        "create_block",
    }
    assert names == expected, f"Outils inattendus ou manquants : {names ^ expected}"


# ---------------------------------------------------------------------------
# 2. list_workspaces
# ---------------------------------------------------------------------------


async def test_list_workspaces_contient_workspace(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(await _list_workspaces(db_pool))
    slugs = [w["slug"] for w in data]
    assert mcp_ws["ws_slug"] in slugs


# ---------------------------------------------------------------------------
# 3. list_types
# ---------------------------------------------------------------------------


async def test_list_types_retourne_epic(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(await _list_types(db_pool, mcp_ws["ws_slug"]))  # type: ignore[arg-type]
    slugs = [t["slug"] for t in data]
    assert "epic" in slugs


async def test_list_types_workspace_inconnu(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(ValueError, match="introuvable"):
        await _list_types(db_pool, "inexistant")


# ---------------------------------------------------------------------------
# 4. list_documents
# ---------------------------------------------------------------------------


async def test_list_documents_contient_doc(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(await _list_documents(db_pool, mcp_ws["ws_slug"]))  # type: ignore[arg-type]
    assert any(d["title"] == "Epic A" for d in data)


async def test_list_documents_workspace_inconnu(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(ValueError, match="introuvable"):
        await _list_documents(db_pool, "nope")


# ---------------------------------------------------------------------------
# 5. get_document
# ---------------------------------------------------------------------------


async def test_get_document_nominal(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _get_document(db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"])  # type: ignore[arg-type]
    )
    assert data["title"] == "Epic A"  # type: ignore[index]
    assert data["contenu"] == "# Epic A"  # type: ignore[index]
    assert data["functional_type_slug"] == "epic"  # type: ignore[index]


async def test_get_document_inconnu(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(await _get_document(db_pool, mcp_ws["ws_slug"], str(uuid.uuid4())))  # type: ignore[arg-type]
    assert "error" in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 6. create_document
# ---------------------------------------------------------------------------


async def test_create_document_nominal(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "block_slug": mcp_ws["block_slug"],
                "title": "Nouveau doc MCP",
                "contenu": "# Contenu",
                "functional_type_slug": mcp_ws["type_slug"],
            },
        )
    )
    assert data["created"] is True  # type: ignore[index]
    assert "id" in data  # type: ignore[operator]


async def test_create_document_type_inconnu(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "block_slug": mcp_ws["block_slug"],
                "title": "Test",
                "functional_type_slug": "inexistant",
            },
        )
    )
    assert "error" in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 7. update_document
# ---------------------------------------------------------------------------


async def test_update_document_titre(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": mcp_ws["doc_id"],
                "title": "Epic A — modifié",
            },
        )
    )
    assert data["updated"] is True  # type: ignore[index]

    check = _json(await _get_document(db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"]))  # type: ignore[arg-type]
    assert check["title"] == "Epic A — modifié"  # type: ignore[index]


async def test_update_document_inconnu(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": str(uuid.uuid4()),
                "title": "Ghost",
            },
        )
    )
    assert "error" in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 8. list_property_values
# ---------------------------------------------------------------------------


async def test_list_property_values_retourne_prop(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _list_property_values(
            db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"]  # type: ignore[arg-type]
        )
    )
    assert isinstance(data, list)
    slugs = [p["prop_slug"] for p in data]  # type: ignore[union-attr]
    assert "priority" in slugs


# ---------------------------------------------------------------------------
# 9. get_property_value
# ---------------------------------------------------------------------------


async def test_get_property_value_vide(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _get_property_value(
            db_pool,
            mcp_ws["ws_slug"],  # type: ignore[arg-type]
            mcp_ws["doc_id"],  # type: ignore[arg-type]
            "priority",
        )
    )
    assert data["prop_slug"] == "priority"  # type: ignore[index]
    assert data["value"] is None  # type: ignore[index]


async def test_get_property_value_introuvable(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _get_property_value(
            db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"], "inexistant"  # type: ignore[arg-type]
        )
    )
    assert "error" in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 10. set_property_value → puis get vérifie la valeur
# ---------------------------------------------------------------------------


async def test_set_then_get_property_value(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    set_result = _json(
        await _set_property_value(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": mcp_ws["doc_id"],
                "prop_slug": "priority",
                "value": "haute",
            },
        )
    )
    assert set_result["updated"] is True  # type: ignore[index]

    get_result = _json(
        await _get_property_value(
            db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"], "priority"  # type: ignore[arg-type]
        )
    )
    assert get_result["value"] == "haute"  # type: ignore[index]


async def test_set_property_value_double_field_interdit(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Fournir value ET allowed_value_slug en même temps doit lever une erreur."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await _set_property_value(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": mcp_ws["doc_id"],
                "prop_slug": "priority",
                "value": "haute",
                "allowed_value_slug": "haute",
            },
        )


# ---------------------------------------------------------------------------
# 11. list_templates
# ---------------------------------------------------------------------------


async def test_list_templates_retourne_liste(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    data = _json(await _list_templates())
    assert isinstance(data, list)
    for tpl in data:  # type: ignore[union-attr]
        assert "template" in tpl
        assert "version" in tpl
        assert isinstance(tpl["type_slugs"], list)


# ---------------------------------------------------------------------------
# 12. create_workspace
# ---------------------------------------------------------------------------


async def test_create_workspace_nominal(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    data = _json(
        await _create_workspace(
            db_pool,
            {"slug": "mcp-new-ws", "label": "Nouveau WS MCP", "description": "Test"},
        )
    )
    assert data["created"] is True  # type: ignore[index]
    assert data["slug"] == "mcp-new-ws"  # type: ignore[index]
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "mcp-new-ws")


async def test_create_workspace_slug_duplique(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _create_workspace(
            db_pool, {"slug": mcp_ws["ws_slug"], "label": "Doublon"}
        )
    )
    assert "error" in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 13. import_template + create_block
# ---------------------------------------------------------------------------


async def test_import_template_idempotent(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Si aucun template installé, le test passe en no-op ; sinon vérifie l'idempotence."""
    configure(db_pool)
    templates_data = _json(await _list_templates())
    if not templates_data:
        pytest.skip("Aucun template installé sur ce serveur")

    tpl_slug = templates_data[0]["template"]  # type: ignore[index]
    ws = mcp_ws["ws_slug"]

    r1 = _json(await _import_template(db_pool, {"workspace_slug": ws, "template_slug": tpl_slug}))
    assert r1["applied"] is True  # type: ignore[index]
    assert r1["no_op"] is False  # type: ignore[index]

    r2 = _json(await _import_template(db_pool, {"workspace_slug": ws, "template_slug": tpl_slug}))
    assert r2["no_op"] is True  # type: ignore[index]


async def test_import_template_inconnu(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    configure(db_pool)
    data = _json(
        await _import_template(
            db_pool,
            {"workspace_slug": mcp_ws["ws_slug"], "template_slug": "inexistant"},
        )
    )
    assert "error" in data  # type: ignore[operator]


async def test_create_block_nominal(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    configure(db_pool)
    data = _json(
        await _create_block(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "slug": "mcp-bloc-camp",
                "label": "Bloc campagne MCP",
                "functional_type_slug": mcp_ws["type_slug"],
            },
        )
    )
    assert data["created"] is True  # type: ignore[index]
    assert data["slug"] == "mcp-bloc-camp"  # type: ignore[index]


async def test_create_block_type_inconnu(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    configure(db_pool)
    data = _json(
        await _create_block(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "slug": "bloc-bad-type",
                "label": "Bad",
                "functional_type_slug": "type-inexistant",
            },
        )
    )
    assert "error" in data  # type: ignore[operator]


async def test_create_block_avec_template(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """create_block avec template_slug importe le template puis crée le bloc."""
    configure(db_pool)
    templates_data = _json(await _list_templates())
    if not templates_data:
        pytest.skip("Aucun template installé sur ce serveur")

    tpl = templates_data[0]  # type: ignore[index]
    tpl_slug = tpl["template"]
    type_slug = tpl["type_slugs"][0]

    data = _json(
        await _create_block(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "slug": "bloc-via-tpl",
                "label": "Bloc via template",
                "functional_type_slug": type_slug,
                "template_slug": tpl_slug,
            },
        )
    )
    assert data["created"] is True  # type: ignore[index]


# ---------------------------------------------------------------------------
# 14. Dispatch _call_tool
# ---------------------------------------------------------------------------


async def test_call_tool_outil_inconnu(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    data = _json(await _call_tool("outil_inexistant", {}))
    assert "error" in data  # type: ignore[operator]


async def test_call_tool_list_workspaces(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    configure(db_pool)
    data = _json(await _call_tool("list_workspaces", {}))
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# 15. Profil API is_admin — flag schema + service
# ---------------------------------------------------------------------------


async def test_api_profile_is_admin_defaut_false(db_pool: asyncpg.Pool) -> None:
    """Un profil créé sans is_admin doit avoir is_admin=False."""
    from docflow.apikeys.schemas import ApiProfileCreate
    from docflow.apikeys.service import create_profile, delete_profile

    owner_id = uuid.uuid4()
    await db_pool.execute(
        "INSERT INTO app_user (id, email, label, password_hash, is_admin, validated) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        owner_id, f"{owner_id}@test.local", "Test", "x", False, True,
    )
    body = ApiProfileCreate(name="profil-non-admin", description=None)
    profile = await create_profile(db_pool, owner_id, body)
    assert profile.is_admin is False
    await delete_profile(db_pool, owner_id, profile.id)
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner_id)


async def test_api_profile_is_admin_true(db_pool: asyncpg.Pool) -> None:
    """Un profil créé avec is_admin=True doit le conserver."""
    from docflow.apikeys.schemas import ApiProfileCreate
    from docflow.apikeys.service import create_profile, delete_profile, list_profiles

    owner_id = uuid.uuid4()
    await db_pool.execute(
        "INSERT INTO app_user (id, email, label, password_hash, is_admin, validated) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        owner_id, f"{owner_id}@test.local", "Test Admin", "x", False, True,
    )
    body = ApiProfileCreate(name="profil-admin", description=None, is_admin=True)
    profile = await create_profile(db_pool, owner_id, body)
    assert profile.is_admin is True

    profiles = await list_profiles(db_pool, owner_id)
    match = next(p for p in profiles if p.id == profile.id)
    assert match.is_admin is True

    await delete_profile(db_pool, owner_id, profile.id)
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner_id)


async def test_resolve_api_key_retourne_profile_is_admin(db_pool: asyncpg.Pool) -> None:
    """resolve_api_key doit retourner (user, scopes, profile_is_admin)."""
    from docflow.apikeys.schemas import ApiKeyCreate, ApiProfileCreate
    from docflow.apikeys.service import (
        create_profile,
        delete_profile,
        generate_key,
        resolve_api_key,
    )

    owner_id = uuid.uuid4()
    await db_pool.execute(
        "INSERT INTO app_user (id, email, label, password_hash, is_admin, validated) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        owner_id, f"{owner_id}@resolvetest.local", "Resolve", "x", False, True,
    )
    profile = await create_profile(
        db_pool, owner_id, ApiProfileCreate(name="admin-prof", is_admin=True)
    )
    key_created = await generate_key(
        db_pool, owner_id, ApiKeyCreate(profile_id=profile.id, label="test-key")
    )
    raw_key = key_created.key

    user, scopes, profile_is_admin = await resolve_api_key(db_pool, raw_key)
    assert profile_is_admin is True
    assert user.id == owner_id

    await delete_profile(db_pool, owner_id, profile.id)
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner_id)

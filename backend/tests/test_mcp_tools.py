"""Campagne de tests complète des 20 outils MCP + flag is_admin sur les profils API.

Chaque test appelle les handlers directement (pas via SSE) pour isoler la logique.
Couverture : chemin nominal, erreur métier, idempotence, guard admin.
"""

from __future__ import annotations

import json
import pathlib
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import yaml
from mcp.types import CallToolResult

import docflow.mcp.server as mcp_server_mod
from docflow.mcp.server import (
    _TOOLS,
    _block_exists,
    _call_tool,
    _create_block,
    _create_document,
    _create_workspace,
    _delete_block,
    _delete_document,
    _export_template,
    _finalize_tool_result,
    _get_block_type,
    _get_document,
    _get_property_value,
    _get_template_yaml,
    _import_template,
    _list_blocks,
    _list_documents,
    _list_property_values,
    _list_templates,
    _list_types,
    _list_workspaces,
    _set_document_parent,
    _set_property_value,
    _update_document,
    _workspace_exists,
    configure,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json(result: list) -> object:
    return json.loads((result.content if hasattr(result, "content") else result)[0].text)


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


@pytest.fixture()
async def mcp_session(db_pool: asyncpg.Pool) -> AsyncIterator[uuid.UUID]:
    """Session MCP authentifiée (identité JWT-like) pour les outils d'écriture.

    create_workspace estampille désormais owner_id = utilisateur agissant : une
    session doit être liée au contexte. Cède l'id de l'utilisateur système.
    """
    from docflow.mcp.session import McpSession, reset_current_session, set_current_session
    from docflow.schemas.auth import AuthUser

    row = await db_pool.fetchrow(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, true) "
        "ON CONFLICT (email) DO UPDATE SET label = EXCLUDED.label RETURNING id",
        "mcp-tools@test.local",
        "MCP Tools",
    )
    assert row is not None
    uid: uuid.UUID = row["id"]
    # Superadmin : bypass de l'accès-utilisateur (les workspaces des fixtures
    # sont créés en SQL avec owner NULL — l'enforcement les refuserait sinon).
    user = AuthUser(
        id=uid,
        email="mcp-tools@test.local",
        label="MCP Tools",
        is_admin=True,
        validated=True,
        disabled=False,
    )
    token = set_current_session(McpSession(user=user))
    try:
        yield uid
    finally:
        reset_current_session(token)
        await db_pool.execute("DELETE FROM app_user WHERE email = 'mcp-tools@test.local'")


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
        "export_template",
        "get_template_yaml",
        "create_workspace",
        "import_template",
        "create_block",
        "create_api_profile",
        "generate_api_key",
        "set_document_parent",
        "delete_document",
        "sync_child_documents",
        "workspace_exists",
        "block_exists",
        "get_block_type",
        "list_blocks",
        "delete_block",
        "create_upload",
        "create_artifact",
        "update_artifact",
        "patch_artifact",
        "prune_artifact_revisions",
        "get_artifact",
        "get_artifact_link",
        "get_preview_link",
        "get_maquette_png",
        "get_artifact_data",
        "list_artifacts",
        "list_block_properties",
        "list_block_objects",
        "query_documents",
        "list_block_tree",
        "find_by_dedup_key",
        "set_dedup_key",
        "list_workspace_members",
        "add_workspace_member",
        "remove_workspace_member",
        "find_referencing_documents",
        "search_documents",
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


async def test_list_types_retourne_epic(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
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


async def test_get_document_nominal(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    data = _json(
        await _get_document(db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"])  # type: ignore[arg-type]
    )
    assert data["title"] == "Epic A"  # type: ignore[index]
    assert data["contenu"] == "# Epic A"  # type: ignore[index]
    assert data["functional_type_slug"] == "epic"  # type: ignore[index]


async def test_get_document_inconnu(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    data = _json(await _get_document(db_pool, mcp_ws["ws_slug"], str(uuid.uuid4())))  # type: ignore[arg-type]
    assert "error" in data  # type: ignore[operator]


async def test_get_document_doc_id_malforme(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Un doc_id qui n'est pas un UUID doit renvoyer {"error": ...}, pas lever ValueError."""
    data = _json(await _get_document(db_pool, mcp_ws["ws_slug"], "pas-un-uuid"))  # type: ignore[arg-type]
    assert "error" in data  # type: ignore[operator]


async def test_get_document_warns_required_unset(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Une propriété obligatoire ajoutée après création (donc non renseignée)
    déclenche un warning consultatif dans get_document (cas legacy : le contrat
    dur ne protège que la création)."""
    await db_pool.execute(
        "INSERT INTO properties_defs (slug, label, type, functional_type_ref, required) "
        "VALUES ($1, $2, $3, $4, true)",
        "statut",
        "Statut",
        "text",
        mcp_ws["type_id"],
    )
    data = _json(await _get_document(db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"]))  # type: ignore[arg-type]
    warnings = data.get("warnings")  # type: ignore[union-attr]
    assert warnings, "un warning est attendu pour la required non renseignée"
    assert "statut" in warnings[0]


async def test_get_document_no_warning_when_satisfied(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Une required renseignée ne déclenche aucun warning."""
    await db_pool.execute(
        "INSERT INTO properties_defs (slug, label, type, functional_type_ref, required) "
        "VALUES ($1, $2, $3, $4, true)",
        "statut",
        "Statut",
        "text",
        mcp_ws["type_id"],
    )
    _json(
        await _set_property_value(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": mcp_ws["doc_id"],
                "prop_slug": "statut",
                "value": "a_cadrer",
            },
        )
    )
    data = _json(await _get_document(db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"]))  # type: ignore[arg-type]
    assert "warnings" not in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 6. create_document
# ---------------------------------------------------------------------------


async def test_create_document_nominal(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
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


# Bug MCO : create_document doit appliquer la contrainte de type de position
# (racine du bloc = type du bloc ; sous un parent = fils direct du type du parent),
# au même titre que set_document_parent. Les 4 combinaisons sont couvertes.


@pytest.fixture()
async def mcp_feature_type(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    """Ajoute un type 'feature' enfant direct de 'epic' au workspace de la fixture."""
    await db_pool.execute(
        "INSERT INTO functional_type (slug, label, workspace_technical_key, parent) "
        "VALUES ($1, $2, $3, $4)",
        "feature",
        "Feature",
        mcp_ws["wk"],
        mcp_ws["type_id"],
    )


async def test_create_document_racine_type_incorrect_refuse(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object], mcp_feature_type: None
) -> None:
    # Bloc 'epics' typé epic ; poser un 'feature' à la racine (parent omis) → refus.
    data = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "block_slug": mcp_ws["block_slug"],
                "title": "Feature à la racine",
                "functional_type_slug": "feature",
            },
        )
    )
    assert "error" in data  # type: ignore[operator]


async def test_create_document_racine_type_correct_ok(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "block_slug": mcp_ws["block_slug"],
                "title": "Epic racine",
                "functional_type_slug": mcp_ws["type_slug"],
            },
        )
    )
    assert data["created"] is True  # type: ignore[index]


async def test_create_document_enfant_type_correct_ok(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object], mcp_feature_type: None
) -> None:
    data = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "block_slug": mcp_ws["block_slug"],
                "title": "Feature sous epic",
                "functional_type_slug": "feature",
                "parent_id": mcp_ws["doc_id"],
            },
        )
    )
    assert data["created"] is True  # type: ignore[index]


async def test_create_document_enfant_type_invalide_refuse(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object], mcp_feature_type: None
) -> None:
    # 'epic' n'est pas un fils direct de 'epic' → refus sous le parent epic.
    data = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "block_slug": mcp_ws["block_slug"],
                "title": "Epic sous epic",
                "functional_type_slug": mcp_ws["type_slug"],
                "parent_id": mcp_ws["doc_id"],
            },
        )
    )
    assert "error" in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 7. update_document
# ---------------------------------------------------------------------------


async def test_update_document_titre(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    data = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": mcp_ws["doc_id"],
                "title": "Epic A — modifié",
                "expected_version": 1,
            },
        )
    )
    assert data["updated"] is True  # type: ignore[index]
    # Le retour porte la NOUVELLE version, directement réutilisable en écriture.
    assert data["version"] == 2  # type: ignore[index]

    check = _json(await _get_document(db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"]))  # type: ignore[arg-type]
    assert check["title"] == "Epic A — modifié"  # type: ignore[index]
    assert check["version"] == 2  # type: ignore[index]
    assert check["is_current"] is True  # type: ignore[index]


async def test_update_document_inconnu(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    data = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": str(uuid.uuid4()),
                "title": "Ghost",
                "expected_version": 1,
            },
        )
    )
    assert data["error"]["code"] == "not_found"  # type: ignore[index]


async def test_update_document_doc_id_malforme(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": "pas-un-uuid",
                "title": "Ghost",
                "expected_version": 1,
            },
        )
    )
    assert "error" in data  # type: ignore[operator]


async def test_update_document_sans_version_refuse(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Bascule franche : expected_version obligatoire (pas d'écriture aveugle)."""
    data = _json(
        await _update_document(
            db_pool,
            {"workspace_slug": mcp_ws["ws_slug"], "doc_id": mcp_ws["doc_id"], "title": "X"},
        )
    )
    assert data["error"]["code"] == "version_required"  # type: ignore[index]
    # Refus = aucune écriture : le document reste à sa version initiale.
    check = _json(await _get_document(db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"]))  # type: ignore[arg-type]
    assert check["version"] == 1  # type: ignore[index]
    assert check["title"] == "Epic A"  # type: ignore[index]


async def test_update_document_version_perimee_refuse(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Conflit optimiste : version périmée → refus discriminable, sans écrasement."""
    ws, doc_id = mcp_ws["ws_slug"], mcp_ws["doc_id"]
    # Première écriture : passe la version à 2.
    ok = _json(
        await _update_document(
            db_pool,
            {"workspace_slug": ws, "doc_id": doc_id, "contenu": "v2", "expected_version": 1},
        )
    )
    assert ok["version"] == 2  # type: ignore[index]
    # Deuxième écriture sur la version 1 périmée : refus.
    conflict = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": ws,
                "doc_id": doc_id,
                "contenu": "écrasement",
                "expected_version": 1,
            },
        )
    )
    err = conflict["error"]  # type: ignore[index]
    assert err["code"] == "version_conflict"
    # L'erreur porte l'état COURANT pour réappliquer sans relecture.
    assert err["version"] == 2
    assert err["contenu"] == "v2"
    # Aucun écrasement : le contenu courant est intact.
    got = _json(await _get_document(db_pool, ws, doc_id))  # type: ignore[arg-type]
    assert got["contenu"] == "v2"  # type: ignore[index]
    assert got["version"] == 2  # type: ignore[index]


async def test_update_conflict_code_distinct_du_not_found(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Le code du conflit est distinct de celui du document introuvable."""
    ws, doc_id = mcp_ws["ws_slug"], mcp_ws["doc_id"]
    conflict = _json(
        await _update_document(
            db_pool,
            {"workspace_slug": ws, "doc_id": doc_id, "title": "z", "expected_version": 99},
        )
    )
    not_found = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": ws,
                "doc_id": str(uuid.uuid4()),
                "title": "z",
                "expected_version": 1,
            },
        )
    )
    assert conflict["error"]["code"] == "version_conflict"  # type: ignore[index]
    assert not_found["error"]["code"] == "not_found"  # type: ignore[index]


# Bug MCO : omission d'un champ (title ou contenu) ne doit PAS écraser l'autre à NULL.
# Les deux cas d'omission sont testés dans la même suite (symétrie).


async def test_update_document_titre_seul_preserve_contenu(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    ws, doc_id = mcp_ws["ws_slug"], mcp_ws["doc_id"]
    # Le doc de la fixture a été créé avec contenu "# Epic A".
    res = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": ws,
                "doc_id": doc_id,
                "title": "Epic A renommé",
                "expected_version": 1,
            },
        )
    )
    assert res["updated"] is True  # type: ignore[index]
    got = _json(await _get_document(db_pool, ws, doc_id))  # type: ignore[arg-type]
    assert got["title"] == "Epic A renommé"  # type: ignore[index]
    # Le contenu omis doit être reporté depuis la version précédente, pas mis à NULL.
    assert got["contenu"] == "# Epic A"  # type: ignore[index]


async def test_update_document_contenu_seul_preserve_titre(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    ws, doc_id = mcp_ws["ws_slug"], mcp_ws["doc_id"]
    res = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": ws,
                "doc_id": doc_id,
                "contenu": "# Nouveau corps",
                "expected_version": 1,
            },
        )
    )
    assert res["updated"] is True  # type: ignore[index]
    got = _json(await _get_document(db_pool, ws, doc_id))  # type: ignore[arg-type]
    # Le titre omis doit rester inchangé.
    assert got["title"] == "Epic A"  # type: ignore[index]
    assert got["contenu"] == "# Nouveau corps"  # type: ignore[index]


async def test_update_document_deux_champs(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    ws, doc_id = mcp_ws["ws_slug"], mcp_ws["doc_id"]
    res = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": ws,
                "doc_id": doc_id,
                "title": "T2",
                "contenu": "C2",
                "expected_version": 1,
            },
        )
    )
    assert res["updated"] is True  # type: ignore[index]
    got = _json(await _get_document(db_pool, ws, doc_id))  # type: ignore[arg-type]
    assert got["title"] == "T2"  # type: ignore[index]
    assert got["contenu"] == "C2"  # type: ignore[index]


async def test_update_document_sans_champ_refuse(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    ws, doc_id = mcp_ws["ws_slug"], mcp_ws["doc_id"]
    res = _json(await _update_document(db_pool, {"workspace_slug": ws, "doc_id": doc_id}))
    assert "error" in res  # type: ignore[operator]


async def test_get_document_version_anterieure(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """get_document(version=N) restitue titre+contenu d'alors, sans effet de bord."""
    ws, doc_id = mcp_ws["ws_slug"], mcp_ws["doc_id"]
    # Fixture : v1 = "# Epic A". On écrit une v2.
    await _update_document(
        db_pool,
        {"workspace_slug": ws, "doc_id": doc_id, "contenu": "corps v2", "expected_version": 1},
    )
    v1 = _json(await _get_document(db_pool, ws, doc_id, 1))  # type: ignore[arg-type]
    assert v1["contenu"] == "# Epic A"  # type: ignore[index]
    assert v1["version"] == 1  # type: ignore[index]
    assert v1["is_current"] is False  # type: ignore[index]

    v2 = _json(await _get_document(db_pool, ws, doc_id, 2))  # type: ignore[arg-type]
    assert v2["contenu"] == "corps v2"  # type: ignore[index]
    assert v2["is_current"] is True  # type: ignore[index]

    # La lecture d'une version ne crée aucune révision : le head reste à 2.
    cur = _json(await _get_document(db_pool, ws, doc_id))  # type: ignore[arg-type]
    assert cur["version"] == 2  # type: ignore[index]


async def test_get_document_version_inexistante_donne_les_bornes(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    ws, doc_id = mcp_ws["ws_slug"], mcp_ws["doc_id"]
    data = _json(await _get_document(db_pool, ws, doc_id, 99))  # type: ignore[arg-type]
    err = data["error"]  # type: ignore[index]
    assert err["code"] == "version_not_found"
    assert err["available_min"] == 1
    assert err["available_max"] == 1


async def test_get_document_version_malformee(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    ws, doc_id = mcp_ws["ws_slug"], mcp_ws["doc_id"]
    data = _json(await _get_document(db_pool, ws, doc_id, "abc"))  # type: ignore[arg-type]
    assert "error" in data  # type: ignore[operator]


async def test_create_document_retourne_version(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """create_document expose la version initiale (utilisable en expected_version)."""
    data = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "block_slug": mcp_ws["block_slug"],
                "title": "Epic Neuf",
                "contenu": "# Neuf",
                "functional_type_slug": "epic",
            },
        )
    )
    assert data["created"] is True  # type: ignore[index]
    assert data["version"] == 1  # type: ignore[index]
    # La version initiale permet un update immédiat sans relecture.
    upd = _json(
        await _update_document(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": data["id"],  # type: ignore[index]
                "contenu": "# Neuf v2",
                "expected_version": data["version"],  # type: ignore[index]
            },
        )
    )
    assert upd["version"] == 2  # type: ignore[index]


# ---------------------------------------------------------------------------
# 8. list_property_values
# ---------------------------------------------------------------------------


async def test_list_property_values_retourne_prop(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _list_property_values(
            db_pool,
            mcp_ws["ws_slug"],
            mcp_ws["doc_id"],  # type: ignore[arg-type]
        )
    )
    assert isinstance(data, list)
    slugs = [p["prop_slug"] for p in data]  # type: ignore[union-attr]
    assert "priority" in slugs
    # Chaque entrée expose le flag required (ici priority n'est pas obligatoire)
    priority = next(p for p in data if p["prop_slug"] == "priority")  # type: ignore[union-attr,index]
    assert priority["required"] is False


async def test_list_property_values_doc_id_malforme(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _list_property_values(
            db_pool,
            mcp_ws["ws_slug"],  # type: ignore[arg-type]
            "pas-un-uuid",
        )
    )
    assert "error" in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 9. get_property_value
# ---------------------------------------------------------------------------


async def test_get_property_value_vide(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
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
            db_pool,
            mcp_ws["ws_slug"],
            mcp_ws["doc_id"],
            "inexistant",  # type: ignore[arg-type]
        )
    )
    assert "error" in data  # type: ignore[operator]


async def test_get_property_value_doc_id_malforme(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _get_property_value(
            db_pool,
            mcp_ws["ws_slug"],  # type: ignore[arg-type]
            "pas-un-uuid",
            "priority",
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
            db_pool,
            mcp_ws["ws_slug"],
            mcp_ws["doc_id"],
            "priority",  # type: ignore[arg-type]
        )
    )
    assert get_result["value"] == "haute"  # type: ignore[index]


async def test_set_property_value_double_field_interdit(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Fournir value ET allowed_value_slug en même temps doit renvoyer un refus
    JSON structuré {"error": ...} — jamais une HTTPException qui remonte au SDK."""
    data = _json(
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
    )
    assert "error" in data  # type: ignore[operator]


async def test_set_property_value_uuid_invalide(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """doc_id malformé → refus JSON propre, pas une exception qui remonte au SDK."""
    data = _json(
        await _set_property_value(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": "pas-un-uuid",
                "prop_slug": "priority",
                "value": "haute",
            },
        )
    )
    assert data == {"error": "doc_id : UUID invalide"}


async def test_set_property_value_conflit_de_version(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Deux écritures concurrentes avec un expected_version périmée : le conflit
    409 (detail structuré côté service) doit ressortir en JSON exploitable,
    jamais en str(dict) façon repr Python."""
    first = _json(
        await _set_property_value(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": mcp_ws["doc_id"],
                "prop_slug": "priority",
                "value": "haute",
                "expected_version": 0,
            },
        )
    )
    assert first["updated"] is True  # type: ignore[index]

    stale = _json(
        await _set_property_value(
            db_pool,
            {
                "workspace_slug": mcp_ws["ws_slug"],
                "doc_id": mcp_ws["doc_id"],
                "prop_slug": "priority",
                "value": "basse",
                "expected_version": 0,
            },
        )
    )
    assert isinstance(stale, dict)
    assert isinstance(stale["error"], dict)  # type: ignore[index]
    assert stale["error"]["version"] == 1  # type: ignore[index]
    assert stale["error"]["value"] == "haute"  # type: ignore[index]


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
# 11bis. export_template / get_template_yaml (lecture pour agents)
# ---------------------------------------------------------------------------

_MCP_TPL = {
    "version": 2,
    "template": "mcp-tpl",
    "label": "Modèle MCP",
    "functional_types": [
        {
            "slug": "base",
            "label": "Base",
            "abstract": True,
            "properties": [{"slug": "statut", "label": "Statut", "type": "text"}],
        },
        {
            "slug": "epic",
            "label": "Epic",
            "inherit": "base",
            "properties": [{"slug": "titre", "label": "Titre", "type": "text"}],
        },
    ],
}


@pytest.fixture()
def mcp_templates_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    (tmp_path / "mcp-tpl.yaml").write_text(yaml.dump(_MCP_TPL, allow_unicode=True))
    monkeypatch.setattr(mcp_server_mod, "_TEMPLATES_DIR", tmp_path)
    return tmp_path


async def test_export_template_mcp_flattens(mcp_templates_dir: pathlib.Path) -> None:
    data = _json(await _export_template("mcp-tpl"))
    assert data["template"] == "mcp-tpl"  # type: ignore[index]
    assert data["version"] == 2  # type: ignore[index]
    types = {t["slug"]: t for t in data["functional_types"]}  # type: ignore[index]
    # Type abstract exclu ; propriété héritée aplatie sur le concret.
    assert set(types) == {"epic"}
    prop_slugs = [p["slug"] for p in types["epic"]["properties"]]
    assert "statut" in prop_slugs and "titre" in prop_slugs


async def test_export_template_mcp_unknown(mcp_templates_dir: pathlib.Path) -> None:
    data = _json(await _export_template("inconnu"))
    assert "error" in data  # type: ignore[operator]


async def test_get_template_yaml_mcp(mcp_templates_dir: pathlib.Path) -> None:
    data = _json(await _get_template_yaml("mcp-tpl"))
    assert data["template"] == "mcp-tpl"  # type: ignore[index]
    # Source native : l'héritage (inherit/abstract) est présent, non résolu.
    assert "inherit" in data["yaml_content"]  # type: ignore[index]


async def test_get_template_yaml_mcp_unknown(mcp_templates_dir: pathlib.Path) -> None:
    data = _json(await _get_template_yaml("inconnu"))
    assert "error" in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 12. create_workspace
# ---------------------------------------------------------------------------


async def test_create_workspace_nominal(db_pool: asyncpg.Pool, mcp_session: uuid.UUID) -> None:
    configure(db_pool)
    data = _json(
        await _create_workspace(
            db_pool,
            {"slug": "mcp-new-ws", "label": "Nouveau WS MCP", "description": "Test"},
        )
    )
    assert data["created"] is True  # type: ignore[index]
    assert data["slug"] == "mcp-new-ws"  # type: ignore[index]
    owner = await db_pool.fetchval("SELECT owner_id FROM workspace WHERE slug = $1", "mcp-new-ws")
    assert owner == mcp_session
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "mcp-new-ws")


async def test_create_workspace_slug_duplique(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object], mcp_session: uuid.UUID
) -> None:
    data = _json(await _create_workspace(db_pool, {"slug": mcp_ws["ws_slug"], "label": "Doublon"}))
    assert "error" in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 13. import_template + create_block
# ---------------------------------------------------------------------------


async def test_import_template_idempotent(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
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


async def test_import_template_inconnu(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    configure(db_pool)
    data = _json(
        await _import_template(
            db_pool,
            {"workspace_slug": mcp_ws["ws_slug"], "template_slug": "inexistant"},
        )
    )
    assert "error" in data  # type: ignore[operator]


async def test_create_block_nominal(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
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


async def test_create_block_type_inconnu(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
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


async def test_create_block_avec_template(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
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
# delete_document
# ---------------------------------------------------------------------------


async def test_delete_document_sans_descendant(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Un document sans enfant se supprime sans confirm."""
    ws = str(mcp_ws["ws_slug"])
    data = _json(
        await _delete_document(db_pool, {"workspace_slug": ws, "doc_id": mcp_ws["doc_id"]})
    )
    assert data["deleted"] is True  # type: ignore[index]
    assert data["id"] == mcp_ws["doc_id"]  # type: ignore[index]

    check = _json(await _get_document(db_pool, ws, str(mcp_ws["doc_id"])))
    assert "error" in check  # type: ignore[operator]


async def test_delete_document_avec_descendants_refuse_sans_confirm(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Un document avec descendants est refusé tant que confirm=true n'est pas fourni."""
    ws = str(mcp_ws["ws_slug"])
    await db_pool.execute(
        "INSERT INTO functional_type (slug, label, parent, workspace_technical_key) "
        "VALUES ('story', 'Story', $1, $2)",
        mcp_ws["type_id"],
        mcp_ws["wk"],
    )
    child = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": ws,
                "block_slug": str(mcp_ws["block_slug"]),
                "title": "Story 1",
                "functional_type_slug": "story",
                "parent_id": str(mcp_ws["doc_id"]),
            },
        )
    )
    assert child.get("created") is True, child

    refused = _json(
        await _delete_document(db_pool, {"workspace_slug": ws, "doc_id": mcp_ws["doc_id"]})
    )
    assert refused["dependents"] == 1  # type: ignore[index]
    assert "confirm" in str(refused["error"])

    # Le document et son enfant existent toujours
    still_there = _json(await _get_document(db_pool, ws, str(mcp_ws["doc_id"])))
    assert "error" not in still_there  # type: ignore[operator]

    confirmed = _json(
        await _delete_document(
            db_pool, {"workspace_slug": ws, "doc_id": mcp_ws["doc_id"], "confirm": True}
        )
    )
    assert confirmed["deleted"] is True  # type: ignore[index]

    # Cascade DB : l'enfant a disparu avec le parent
    child_gone = _json(await _get_document(db_pool, ws, str(child["id"])))
    assert "error" in child_gone  # type: ignore[operator]


async def test_delete_document_avec_descendants_finalize_is_error(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Le refus à clés multiples ({"error": ..., "dependents": N}) doit porter
    isError=True une fois passé par _finalize_tool_result (bug isError manquant
    dès que le payload d'erreur a plus d'une clé)."""
    ws = str(mcp_ws["ws_slug"])
    await db_pool.execute(
        "INSERT INTO functional_type (slug, label, parent, workspace_technical_key) "
        "VALUES ('story', 'Story', $1, $2)",
        mcp_ws["type_id"],
        mcp_ws["wk"],
    )
    child = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": ws,
                "block_slug": str(mcp_ws["block_slug"]),
                "title": "Story 1",
                "functional_type_slug": "story",
                "parent_id": str(mcp_ws["doc_id"]),
            },
        )
    )
    assert child.get("created") is True, child

    result = await _delete_document(db_pool, {"workspace_slug": ws, "doc_id": mcp_ws["doc_id"]})
    finalized = _finalize_tool_result(result)
    assert isinstance(finalized, CallToolResult)
    assert finalized.isError is True
    payload = json.loads(finalized.content[0].text)
    assert payload["dependents"] == 1


async def test_delete_document_inconnu(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    data = _json(
        await _delete_document(
            db_pool, {"workspace_slug": mcp_ws["ws_slug"], "doc_id": str(uuid.uuid4())}
        )
    )
    assert "error" in data  # type: ignore[operator]


async def test_delete_document_uuid_invalide(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(
        await _delete_document(
            db_pool, {"workspace_slug": mcp_ws["ws_slug"], "doc_id": "pas-un-uuid"}
        )
    )
    assert data == {"error": "doc_id : UUID invalide"}


# ---------------------------------------------------------------------------
# workspace_exists
# ---------------------------------------------------------------------------


async def test_workspace_exists_vrai(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    data = _json(await _workspace_exists(db_pool, str(mcp_ws["ws_slug"])))
    assert data == {"exists": True}


async def test_workspace_exists_faux(db_pool: asyncpg.Pool) -> None:
    data = _json(await _workspace_exists(db_pool, "workspace-qui-nexiste-pas"))
    assert data == {"exists": False}


# ---------------------------------------------------------------------------
# block_exists
# ---------------------------------------------------------------------------


async def test_block_exists_vrai(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    data = _json(await _block_exists(db_pool, str(mcp_ws["ws_slug"]), str(mcp_ws["block_slug"])))
    assert data == {"exists": True}


async def test_block_exists_faux_bloc_inconnu(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(await _block_exists(db_pool, str(mcp_ws["ws_slug"]), "bloc-inexistant"))
    assert data == {"exists": False}


async def test_block_exists_faux_workspace_inconnu(db_pool: asyncpg.Pool) -> None:
    data = _json(await _block_exists(db_pool, "ws-inexistant", "peu-importe"))
    assert data == {"exists": False}


# ---------------------------------------------------------------------------
# get_block_type
# ---------------------------------------------------------------------------


async def test_get_block_type_nominal(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    data = _json(await _get_block_type(db_pool, str(mcp_ws["ws_slug"]), str(mcp_ws["block_slug"])))
    assert data["functional_type_slug"] == "epic"  # type: ignore[index]


async def test_get_block_type_bloc_inconnu(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    data = _json(await _get_block_type(db_pool, str(mcp_ws["ws_slug"]), "bloc-inexistant"))
    assert "error" in data  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 14. Dispatch _call_tool
# ---------------------------------------------------------------------------


async def test_call_tool_outil_inconnu(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    data = _json(await _call_tool("outil_inexistant", {}))
    assert "error" in data  # type: ignore[operator]


async def test_call_tool_list_workspaces(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
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
        owner_id,
        f"{owner_id}@test.local",
        "Test",
        "x",
        False,
        True,
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
        owner_id,
        f"{owner_id}@test.local",
        "Test Admin",
        "x",
        False,
        True,
    )
    body = ApiProfileCreate(name="profil-admin", description=None, is_admin=True)
    profile = await create_profile(db_pool, owner_id, body, caller_is_superadmin=True)
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
        owner_id,
        f"{owner_id}@resolvetest.local",
        "Resolve",
        "x",
        False,
        True,
    )
    profile = await create_profile(
        db_pool,
        owner_id,
        ApiProfileCreate(name="admin-prof", is_admin=True),
        caller_is_superadmin=True,
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


# ---------------------------------------------------------------------------
# set_document_parent
# ---------------------------------------------------------------------------


async def test_set_parent_nominal(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    """Reparente une story (type fils d'epic) d'un epic vers un autre."""
    ws = str(mcp_ws["ws_slug"])
    # type story, fils de epic → valide sous un document epic
    await db_pool.execute(
        "INSERT INTO functional_type (slug, label, parent, workspace_technical_key) "
        "VALUES ('story', 'Story', $1, $2)",
        mcp_ws["type_id"],
        mcp_ws["wk"],
    )
    child = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": ws,
                "block_slug": str(mcp_ws["block_slug"]),
                "title": "Story 1",
                "functional_type_slug": "story",
                "parent_id": str(mcp_ws["doc_id"]),
            },
        )
    )
    assert child.get("created") is True, child
    # Nouveau parent epic à la racine
    parent2 = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": ws,
                "block_slug": str(mcp_ws["block_slug"]),
                "title": "Epic B",
                "functional_type_slug": "epic",
            },
        )
    )
    moved = _json(
        await _set_document_parent(
            db_pool,
            {
                "workspace_slug": ws,
                "doc_id": str(child["id"]),
                "parent_id": str(parent2["id"]),
            },
        )
    )
    assert moved == {
        "updated": True,
        "id": str(child["id"]),
        "parent_id": str(parent2["id"]),
        "functional_type_slug": "story",
    }


async def test_set_parent_type_invalide_guide(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Déplacer un epic racine sous un autre epic → 422 guidant (epic n'est pas fils d'epic)."""
    ws = str(mcp_ws["ws_slug"])
    autre = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": ws,
                "block_slug": str(mcp_ws["block_slug"]),
                "title": "Epic C",
                "functional_type_slug": "epic",
            },
        )
    )
    result = _json(
        await _set_document_parent(
            db_pool,
            {
                "workspace_slug": ws,
                "doc_id": str(mcp_ws["doc_id"]),
                "parent_id": str(autre["id"]),
            },
        )
    )
    assert "re-préciser functional_type_slug" in str(result["error"])


async def test_set_parent_avec_retype_atomique(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Le même déplacement passe quand le type est re-précisé dans le même appel."""
    ws = str(mcp_ws["ws_slug"])
    await db_pool.execute(
        "INSERT INTO functional_type (slug, label, parent, workspace_technical_key) "
        "VALUES ('feature', 'Feature', $1, $2)",
        mcp_ws["type_id"],
        mcp_ws["wk"],
    )
    autre = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": ws,
                "block_slug": str(mcp_ws["block_slug"]),
                "title": "Epic D",
                "functional_type_slug": "epic",
            },
        )
    )
    moved = _json(
        await _set_document_parent(
            db_pool,
            {
                "workspace_slug": ws,
                "doc_id": str(mcp_ws["doc_id"]),
                "parent_id": str(autre["id"]),
                "functional_type_slug": "feature",
            },
        )
    )
    assert moved["updated"] is True
    assert moved["functional_type_slug"] == "feature"
    # Retour à la racine : le type doit redevenir celui du bloc (epic)
    back = _json(
        await _set_document_parent(
            db_pool,
            {
                "workspace_slug": ws,
                "doc_id": str(mcp_ws["doc_id"]),
                "parent_id": None,
                "functional_type_slug": "epic",
            },
        )
    )
    assert back["updated"] is True
    assert back["parent_id"] is None


async def test_set_parent_cycle_refuse(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    """Un document ne peut pas devenir enfant de sa descendance."""
    ws = str(mcp_ws["ws_slug"])
    await db_pool.execute(
        "INSERT INTO functional_type (slug, label, parent, workspace_technical_key) "
        "VALUES ('sub', 'Sub', $1, $2)",
        mcp_ws["type_id"],
        mcp_ws["wk"],
    )
    child = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": ws,
                "block_slug": str(mcp_ws["block_slug"]),
                "title": "Sub 1",
                "functional_type_slug": "sub",
                "parent_id": str(mcp_ws["doc_id"]),
            },
        )
    )
    result = _json(
        await _set_document_parent(
            db_pool,
            {
                "workspace_slug": ws,
                "doc_id": str(mcp_ws["doc_id"]),
                "parent_id": str(child["id"]),
            },
        )
    )
    assert "error" in result


async def test_set_parent_uuid_invalide(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    result = _json(
        await _set_document_parent(
            db_pool,
            {"workspace_slug": str(mcp_ws["ws_slug"]), "doc_id": "pas-un-uuid"},
        )
    )
    assert result == {"error": "doc_id / parent_id : UUID invalide"}


# ---------------------------------------------------------------------------
# Enabler MCO : list_blocks & delete_block
# ---------------------------------------------------------------------------


async def test_list_blocks_retourne_ossature(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    ws = mcp_ws["ws_slug"]
    data = _json(await _list_blocks(db_pool, ws))  # type: ignore[arg-type]
    assert isinstance(data, list)
    epics = next(b for b in data if b["slug"] == mcp_ws["block_slug"])
    assert epics["functional_type_slug"] == mcp_ws["type_slug"]
    assert epics["parent_slug"] is None
    assert "label" in epics and "exposed" in epics


async def test_list_blocks_workspace_inconnu(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    data = _json(await _list_blocks(db_pool, "ws-inexistant"))
    assert "error" in data  # type: ignore[operator]


async def test_delete_block_vide_reussit(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    ws = mcp_ws["ws_slug"]
    # Un bloc vide, sans document.
    created = _json(
        await _create_block(
            db_pool,
            {
                "workspace_slug": ws,
                "slug": "bloc-vide",
                "label": "Bloc vide",
                "functional_type_slug": mcp_ws["type_slug"],
            },
        )
    )
    assert created["created"] is True  # type: ignore[index]

    res = _json(await _delete_block(db_pool, {"workspace_slug": ws, "block_slug": "bloc-vide"}))
    assert res["deleted"] is True  # type: ignore[index]
    # Le bloc disparaît de list_blocks.
    slugs = [b["slug"] for b in _json(await _list_blocks(db_pool, ws))]  # type: ignore[arg-type,union-attr]
    assert "bloc-vide" not in slugs


async def test_delete_block_non_vide_sans_confirm_refuse(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    ws = mcp_ws["ws_slug"]
    # Le bloc de la fixture contient déjà un document (Epic A).
    res = _json(
        await _delete_block(db_pool, {"workspace_slug": ws, "block_slug": mcp_ws["block_slug"]})
    )
    assert "error" in res  # type: ignore[operator]
    assert res["documents"] == 1  # type: ignore[index]
    assert res["dependents"] >= 1  # type: ignore[index]
    # Le bloc est toujours là.
    slugs = [b["slug"] for b in _json(await _list_blocks(db_pool, ws))]  # type: ignore[arg-type,union-attr]
    assert mcp_ws["block_slug"] in slugs


async def test_delete_block_non_vide_avec_confirm_reussit(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    ws = mcp_ws["ws_slug"]
    res = _json(
        await _delete_block(
            db_pool,
            {"workspace_slug": ws, "block_slug": mcp_ws["block_slug"], "confirm": True},
        )
    )
    assert res["deleted"] is True  # type: ignore[index]
    slugs = [b["slug"] for b in _json(await _list_blocks(db_pool, ws))]  # type: ignore[arg-type,union-attr]
    assert mcp_ws["block_slug"] not in slugs


async def test_delete_block_inconnu(db_pool: asyncpg.Pool, mcp_ws: dict[str, object]) -> None:
    res = _json(
        await _delete_block(
            db_pool,
            {"workspace_slug": str(mcp_ws["ws_slug"]), "block_slug": "bloc-fantome"},
        )
    )
    assert "error" in res  # type: ignore[operator]


# ---------------------------------------------------------------------------
# 18. create_api_profile — workspace vérifié + création atomique profil/scope
# ---------------------------------------------------------------------------


async def test_create_api_profile_workspace_inconnu_sans_profil_orphelin(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object], mcp_session: uuid.UUID
) -> None:
    """Un slug de workspace inexistant est refusé, sans laisser de profil sans scope."""
    from docflow.mcp.server import _create_api_profile

    res = _json(
        await _create_api_profile(
            db_pool, {"name": "profil-fantome", "workspace_slug": "ws-qui-nexiste-pas"}
        )
    )
    assert "error" in res  # type: ignore[operator]
    assert "ws-qui-nexiste-pas" in str(res["error"])  # type: ignore[index]
    count = await db_pool.fetchval(
        "SELECT count(*) FROM api_profile WHERE owner_id = $1", mcp_session
    )
    assert count == 0


async def test_create_api_profile_nominal_pose_profil_et_scope(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object], mcp_session: uuid.UUID
) -> None:
    from docflow.mcp.server import _create_api_profile

    res = _json(
        await _create_api_profile(
            db_pool,
            {
                "name": "profil-lecture",
                "workspace_slug": mcp_ws["ws_slug"],
                "read_only": True,
            },
        )
    )
    assert res["created"] is True  # type: ignore[index]
    profile_id = uuid.UUID(str(res["profile_id"]))  # type: ignore[index]
    row = await db_pool.fetchrow(
        "SELECT workspace_slug, block_slug, read_only FROM api_profile_scope WHERE profile_id = $1",
        profile_id,
    )
    assert row is not None
    assert row["workspace_slug"] == mcp_ws["ws_slug"]
    assert row["block_slug"] is None
    assert row["read_only"] is True


async def test_create_api_profile_reste_non_admin(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object], mcp_session: uuid.UUID
) -> None:
    """Garde anti-escalade : un profil créé via MCP n'est jamais admin."""
    from docflow.mcp.server import _create_api_profile

    res = _json(
        await _create_api_profile(
            db_pool,
            {"name": "profil-mcp", "workspace_slug": mcp_ws["ws_slug"], "is_admin": True},
        )
    )
    assert res["created"] is True  # type: ignore[index]
    is_admin = await db_pool.fetchval(
        "SELECT is_admin FROM api_profile WHERE id = $1", uuid.UUID(str(res["profile_id"]))
    )
    assert is_admin is False

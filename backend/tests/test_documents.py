from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreate, DocumentUpdate
from docflow.schemas.properties import AllowedValueCreate, PropertiesDefCreate
from docflow.schemas.property_value import PropertyValueSet
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def test_create_document(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(title="Ma page", content="# Hello", block_id=test_block["id"]),
    )
    assert doc.title == "Ma page"
    assert doc.content == "# Hello"
    assert doc.version == 1
    assert doc.parent_id is None
    assert doc.functional_type_slug is None
    assert doc.workspace_slug == _WS
    assert doc.data_block_ref == test_block["id"]


async def test_create_document_with_type(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    doc = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(title="Epic Doc", functional_type_slug="epic", block_id=test_block["id"]),
    )
    assert doc.functional_type_slug == "epic"
    assert doc.version == 1


async def test_create_document_unknown_type(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    with pytest.raises(HTTPException) as exc:
        await doc_svc.create_document(
            db_pool, _WS,
            DocumentCreate(title="Bad", functional_type_slug="ghost", block_id=test_block["id"]),
        )
    assert exc.value.status_code == 422


async def test_list_documents(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Page A", block_id=test_block["id"])
    )
    await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Page B", block_id=test_block["id"])
    )
    docs = await doc_svc.list_documents(db_pool, _WS)
    titles = [d.title for d in docs]
    assert "Page A" in titles and "Page B" in titles
    # list_documents renvoie head sans contenu (pas de jointure version)
    assert all(d.content is None for d in docs)


async def test_document_parent_hierarchy(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    parent = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Parent", block_id=test_block["id"])
    )
    child = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(
            title="Child",
            parent_id=parent.doc_technical_key,
            block_id=test_block["id"],
        ),
    )
    assert child.parent_id == parent.doc_technical_key


async def test_document_parent_wrong_workspace(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """I-1 : parent doit être dans le même workspace."""
    from docflow.schemas.workspace import WorkspaceCreate
    from docflow.workspaces import service as ws_svc

    other_ws = await ws_svc.create_workspace(
        db_pool, WorkspaceCreate(slug="other-ws", label="Other")
    )
    # Créer un type et un bloc dans l'autre workspace pour pouvoir créer un document
    other_wk: uuid.UUID = other_ws.workspace_technical_key
    other_type_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ($1, $2, $3) RETURNING id",
        "other-root", "Other Root", other_wk,
    )
    other_block_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        "other-block", "Other Block", other_type_id, other_wk,
    )
    parent = await doc_svc.create_document(
        db_pool, "other-ws",
        DocumentCreate(title="Other parent", block_id=other_block_id),
    )
    try:
        with pytest.raises(HTTPException) as exc:
            await doc_svc.create_document(
                db_pool, _WS,
                DocumentCreate(
                    title="Child",
                    parent_id=parent.doc_technical_key,
                    block_id=test_block["id"],
                ),
            )
        assert exc.value.status_code == 422
        assert "I-1" in exc.value.detail
    finally:
        await db_pool.execute(
            "DELETE FROM workspace WHERE workspace_technical_key = $1",
            other_ws.workspace_technical_key,
        )


async def test_get_document_with_content(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(title="Doc", content="# Contenu initial", block_id=test_block["id"]),
    )
    fetched = await doc_svc.get_document(db_pool, _WS, doc.doc_technical_key)
    assert fetched.content == "# Contenu initial"
    assert fetched.version == 1


async def test_update_document_content_versioned(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """DoD 2 : écrire contenu v1 → v2, vérifier version alignée."""
    doc = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(title="Feature A", content="# v1", block_id=test_block["id"]),
    )
    assert doc.version == 1

    updated = await doc_svc.update_document(
        db_pool, _WS, doc.doc_technical_key,
        DocumentUpdate(title="Feature A v2", content="# v2", expected_version=1),
    )
    assert updated.version == 2
    assert updated.title == "Feature A v2"
    assert updated.content == "# v2"

    # La version courante en base est alignée
    refetched = await doc_svc.get_document(db_pool, _WS, doc.doc_technical_key)
    assert refetched.version == 2
    assert refetched.content == "# v2"


async def test_update_document_wrong_version_409(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """Mauvais expected_version → 409 + état courant, base inchangée."""
    doc = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(title="Doc", content="# initial", block_id=test_block["id"]),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.update_document(
            db_pool, _WS, doc.doc_technical_key,
            DocumentUpdate(title="Jamais", content="# jamais", expected_version=99),
        )
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert detail["version"] == 1
    assert detail["title"] == "Doc"
    assert detail["content"] == "# initial"

    # Base inchangée
    refetched = await doc_svc.get_document(db_pool, _WS, doc.doc_technical_key)
    assert refetched.version == 1
    assert refetched.title == "Doc"


async def test_update_document_content_requires_expected_version(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc", block_id=test_block["id"])
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.update_document(
            db_pool, _WS, doc.doc_technical_key,
            DocumentUpdate(content="# new"),  # pas de expected_version
        )
    assert exc.value.status_code == 422


async def test_update_document_metadata_no_version(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """Mise à jour des métadonnées (type fonctionnel) sans expected_version."""
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="story", label="Story"))
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc", block_id=test_block["id"])
    )
    updated = await doc_svc.update_document(
        db_pool, _WS, doc.doc_technical_key,
        DocumentUpdate(functional_type_slug="story"),
    )
    assert updated.functional_type_slug == "story"
    assert updated.version == 1  # pas de bump de version


async def test_update_document_no_changes(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Static", block_id=test_block["id"])
    )
    result = await doc_svc.update_document(
        db_pool, _WS, doc.doc_technical_key, DocumentUpdate()
    )
    assert result.title == "Static"


async def test_get_document_not_found(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    with pytest.raises(HTTPException) as exc:
        await doc_svc.get_document(db_pool, _WS, uuid.uuid4())
    assert exc.value.status_code == 404


async def test_delete_document(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="ToDelete", block_id=test_block["id"])
    )
    await doc_svc.delete_document(db_pool, _WS, doc.doc_technical_key)
    with pytest.raises(HTTPException) as exc:
        await doc_svc.get_document(db_pool, _WS, doc.doc_technical_key)
    assert exc.value.status_code == 404


async def test_delete_document_with_children_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    parent = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Parent", block_id=test_block["id"])
    )
    await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(
            title="Child",
            parent_id=parent.doc_technical_key,
            block_id=test_block["id"],
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.delete_document(db_pool, _WS, parent.doc_technical_key)
    assert exc.value.status_code == 409


# ── Board query (DoD 6) ───────────────────────────────────────────────────────

async def test_board_query_dod6(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """DoD 6 : list_documents filtre par functional_type + prop + allowed_value.

    Crée 3 documents 'feature', positionne statut=done sur 2, statut=todo sur 1.
    Le board doit retourner exactement les 2 features 'done'.
    La jointure utilise idx_pvalue_version_allowed.
    """
    # Crée le type 'feature' avec une prop 'statut' (restricted_list)
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="feature", label="Feature")
    )
    await prop_svc.create_def(
        db_pool, _WS, "feature",
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list"),
    )
    await prop_svc.create_allowed_value(
        db_pool, _WS, "feature", "statut",
        AllowedValueCreate(slug="todo", label="À faire"),
    )
    await prop_svc.create_allowed_value(
        db_pool, _WS, "feature", "statut",
        AllowedValueCreate(slug="done", label="Terminé", position=1),
    )

    feat_a = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(
            title="Feature A", functional_type_slug="feature", block_id=test_block["id"]
        ),
    )
    feat_b = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(
            title="Feature B", functional_type_slug="feature", block_id=test_block["id"]
        ),
    )
    feat_c = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(
            title="Feature C", functional_type_slug="feature", block_id=test_block["id"]
        ),
    )

    # A et B → done ; C → todo
    for doc in (feat_a, feat_b):
        await doc_svc.set_property_value(
            db_pool, _WS, doc.doc_technical_key, "statut",
            PropertyValueSet(allowed_value_slug="done", expected_version=0),
        )
    await doc_svc.set_property_value(
        db_pool, _WS, feat_c.doc_technical_key, "statut",
        PropertyValueSet(allowed_value_slug="todo", expected_version=0),
    )

    # Board : features en statut done
    board = await doc_svc.list_documents(
        db_pool, _WS,
        functional_type="feature",
        prop_slug="statut",
        allowed_value_slug="done",
    )

    titles = {d.title for d in board}
    assert titles == {"Feature A", "Feature B"}
    assert all(d.functional_type_slug == "feature" for d in board)


async def test_board_query_functional_type_only(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """list_documents filtré par functional_type seul (sans valeur)."""
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic")
    )
    await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(title="Epic 1", functional_type_slug="epic", block_id=test_block["id"]),
    )
    await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(title="Epic 2", functional_type_slug="epic", block_id=test_block["id"]),
    )
    # Document sans type fonctionnel
    await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc sans type", block_id=test_block["id"])
    )

    docs = await doc_svc.list_documents(db_pool, _WS, functional_type="epic")
    assert all(d.functional_type_slug == "epic" for d in docs)
    assert {d.title for d in docs} == {"Epic 1", "Epic 2"}

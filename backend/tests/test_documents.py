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
        db_pool,
        _WS,
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
    db_pool: asyncpg.Pool, test_workspace: dict, make_block
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    block_id = await make_block(_WS, "epic", "epic-block")
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Epic Doc", functional_type_slug="epic", block_id=block_id),
    )
    assert doc.functional_type_slug == "epic"
    assert doc.version == 1


async def test_create_document_unknown_type(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    with pytest.raises(HTTPException) as exc:
        await doc_svc.create_document(
            db_pool,
            _WS,
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
        db_pool,
        _WS,
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
        db_pool, WorkspaceCreate(slug="other-ws", label="Other"), None
    )
    # Créer un type et un bloc dans l'autre workspace pour pouvoir créer un document
    other_wk: uuid.UUID = other_ws.workspace_technical_key
    other_type_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ($1, $2, $3) RETURNING id",
        "other-root",
        "Other Root",
        other_wk,
    )
    other_block_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        "other-block",
        "Other Block",
        other_type_id,
        other_wk,
    )
    parent = await doc_svc.create_document(
        db_pool,
        "other-ws",
        DocumentCreate(title="Other parent", block_id=other_block_id),
    )
    try:
        with pytest.raises(HTTPException) as exc:
            await doc_svc.create_document(
                db_pool,
                _WS,
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
        db_pool,
        _WS,
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
        db_pool,
        _WS,
        DocumentCreate(title="Feature A", content="# v1", block_id=test_block["id"]),
    )
    assert doc.version == 1

    updated = await doc_svc.update_document(
        db_pool,
        _WS,
        doc.doc_technical_key,
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
        db_pool,
        _WS,
        DocumentCreate(title="Doc", content="# initial", block_id=test_block["id"]),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.update_document(
            db_pool,
            _WS,
            doc.doc_technical_key,
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


async def test_append_bottom_and_top_literal(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """Append littéral : le fragment est posé au bord du contenu, séparé d'une
    ligne vide, sans tenir compte du titre ni de la structure."""
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Journal", content="# Journal\n\nLigne A.", block_id=test_block["id"]),
    )
    assert doc.version == 1

    bottom = await doc_svc.append_to_document(
        db_pool, _WS, doc.doc_technical_key, content="Ligne B.", position="bottom"
    )
    assert bottom.version == 2
    assert bottom.content == "# Journal\n\nLigne A.\n\nLigne B."

    top = await doc_svc.append_to_document(
        db_pool, _WS, doc.doc_technical_key, content="EN-TÊTE", position="top"
    )
    assert top.version == 3
    # Littéral : posé AVANT le « # Journal », pas après.
    assert top.content == "EN-TÊTE\n\n# Journal\n\nLigne A.\n\nLigne B."


async def test_append_on_empty_document(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """Document sans contenu : l'append pose le fragment seul, sans séparateur."""
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Vide", block_id=test_block["id"])
    )
    appended = await doc_svc.append_to_document(
        db_pool, _WS, doc.doc_technical_key, content="Premier bloc.", position="bottom"
    )
    assert appended.content == "Premier bloc."
    assert appended.version == 2


async def test_append_unknown_document_404(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    with pytest.raises(HTTPException) as exc:
        await doc_svc.append_to_document(db_pool, _WS, uuid.uuid4(), content="x", position="bottom")
    assert exc.value.status_code == 404


async def test_update_document_content_requires_expected_version(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc", block_id=test_block["id"])
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.update_document(
            db_pool,
            _WS,
            doc.doc_technical_key,
            DocumentUpdate(content="# new"),  # pas de expected_version
        )
    assert exc.value.status_code == 422


async def test_update_document_metadata_no_version(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """Mise à jour des métadonnées (type fonctionnel) sans expected_version.

    Le changement de type doit respecter l'invariant de position (DOC-04) : on passe
    d'un type fils du type du parent à un autre type fils (story → bug).
    """
    root_slug: str = test_block["type_slug"]
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="story", label="Story", parent_slug=root_slug)
    )
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="bug", label="Bug", parent_slug=root_slug)
    )
    parent = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Parent", block_id=test_block["id"], functional_type_slug=root_slug),
    )
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Doc",
            block_id=test_block["id"],
            parent_id=parent.doc_technical_key,
            functional_type_slug="story",
        ),
    )
    updated = await doc_svc.update_document(
        db_pool,
        _WS,
        doc.doc_technical_key,
        DocumentUpdate(functional_type_slug="bug"),
    )
    assert updated.functional_type_slug == "bug"
    assert updated.version == 1  # pas de bump de version


async def test_update_document_type_racine_invalide(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """DOC-04 : à la racine d'un bloc, changer le type hors type du bloc → 422."""
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="story", label="Story"))
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc racine", block_id=test_block["id"])
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.update_document(
            db_pool,
            _WS,
            doc.doc_technical_key,
            DocumentUpdate(functional_type_slug="story"),
        )
    assert exc.value.status_code == 422


async def test_update_document_no_changes(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Static", block_id=test_block["id"])
    )
    result = await doc_svc.update_document(db_pool, _WS, doc.doc_technical_key, DocumentUpdate())
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


async def test_delete_document_with_children_cascades(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """0010_document_cascade_delete : supprimer un parent supprime ses enfants
    (ON DELETE CASCADE), plus de rejet 409 — comportement délibérément inversé."""
    parent = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Parent", block_id=test_block["id"])
    )
    child = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Child",
            parent_id=parent.doc_technical_key,
            block_id=test_block["id"],
        ),
    )
    await doc_svc.delete_document(db_pool, _WS, parent.doc_technical_key)
    with pytest.raises(HTTPException) as exc:
        await doc_svc.get_document(db_pool, _WS, child.doc_technical_key)
    assert exc.value.status_code == 404


# ── Board query (DoD 6) ───────────────────────────────────────────────────────


async def test_board_query_dod6(db_pool: asyncpg.Pool, test_workspace: dict, make_block) -> None:
    """DoD 6 : list_documents filtre par functional_type + prop + allowed_value.

    Crée 3 documents 'feature', positionne statut=done sur 2, statut=todo sur 1.
    Le board doit retourner exactement les 2 features 'done'.
    La jointure utilise idx_pvalue_version_allowed.
    """
    # Crée le type 'feature' avec une prop 'statut' (restricted_list)
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="feature", label="Feature"))
    await prop_svc.create_def(
        db_pool,
        _WS,
        "feature",
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list"),
    )
    await prop_svc.create_allowed_value(
        db_pool,
        _WS,
        "feature",
        "statut",
        AllowedValueCreate(slug="todo", label="À faire"),
    )
    await prop_svc.create_allowed_value(
        db_pool,
        _WS,
        "feature",
        "statut",
        AllowedValueCreate(slug="done", label="Terminé", position=1),
    )

    block_id = await make_block(_WS, "feature", "feature-block")
    feat_a = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Feature A", functional_type_slug="feature", block_id=block_id),
    )
    feat_b = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Feature B", functional_type_slug="feature", block_id=block_id),
    )
    feat_c = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Feature C", functional_type_slug="feature", block_id=block_id),
    )

    # A et B → done ; C → todo
    for doc in (feat_a, feat_b):
        await doc_svc.set_property_value(
            db_pool,
            _WS,
            doc.doc_technical_key,
            "statut",
            PropertyValueSet(allowed_value_slug="done", expected_version=0),
        )
    await doc_svc.set_property_value(
        db_pool,
        _WS,
        feat_c.doc_technical_key,
        "statut",
        PropertyValueSet(allowed_value_slug="todo", expected_version=0),
    )

    # Board : features en statut done
    board = await doc_svc.list_documents(
        db_pool,
        _WS,
        functional_type="feature",
        prop_slug="statut",
        allowed_value_slug="done",
    )

    titles = {d.title for d in board}
    assert titles == {"Feature A", "Feature B"}
    assert all(d.functional_type_slug == "feature" for d in board)


async def test_board_query_functional_type_only(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block
) -> None:
    """list_documents filtré par functional_type seul (sans valeur)."""
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    block_id = await make_block(_WS, "epic", "epic-block")
    await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Epic 1", functional_type_slug="epic", block_id=block_id),
    )
    await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Epic 2", functional_type_slug="epic", block_id=block_id),
    )
    # Document sans type fonctionnel (autorisé à la racine : type non contraint)
    await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc sans type", block_id=block_id)
    )

    docs = await doc_svc.list_documents(db_pool, _WS, functional_type="epic")
    assert all(d.functional_type_slug == "epic" for d in docs)
    assert {d.title for d in docs} == {"Epic 1", "Epic 2"}


async def test_document_versions_history(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """Écart n°2 : l'historique des versions est listable et chaque version lisible."""
    from docflow.schemas.document import DocumentUpdate

    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="V1", content="# un", block_id=test_block["id"])
    )
    await doc_svc.update_document(
        db_pool,
        _WS,
        doc.doc_technical_key,
        DocumentUpdate(title="V2", content="# deux", expected_version=1),
    )

    versions = await doc_svc.list_document_versions(db_pool, _WS, doc.doc_technical_key)
    assert [v.version_number for v in versions] == [2, 1]
    assert versions[1].title == "V1"
    assert versions[1].content_length == len("# un")

    v1 = await doc_svc.get_document_version(db_pool, _WS, doc.doc_technical_key, 1)
    assert v1.content == "# un"

    # Version inexistante → 404 explicite.
    with pytest.raises(HTTPException) as exc:
        await doc_svc.get_document_version(db_pool, _WS, doc.doc_technical_key, 99)
    assert exc.value.status_code == 404


async def test_document_author_recorded(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """Écart n°4 : l'auteur de la dernière écriture est porté par le document."""
    from docflow.schemas.document import DocumentUpdate

    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Signé", block_id=test_block["id"]),
        author="G. Aubert",
    )
    assert doc.updated_by == "G. Aubert"

    updated = await doc_svc.update_document(
        db_pool,
        _WS,
        doc.doc_technical_key,
        DocumentUpdate(title="Signé v2", content="x", expected_version=1),
        author="Agent RAG",
    )
    assert updated.updated_by == "Agent RAG"

    # Écriture sans auteur connu : on GARDE le dernier auteur (coalesce),
    # on ne l'efface pas.
    kept = await doc_svc.update_document(
        db_pool,
        _WS,
        doc.doc_technical_key,
        DocumentUpdate(title="Signé v3", content="y", expected_version=2),
    )
    assert kept.updated_by == "Agent RAG"


async def test_delete_document_guard_is_atomic(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """`confirm=False` refuse la cascade DANS la transaction de suppression.

    Le décompte des descendants était fait par l'appelant, dans une transaction
    distincte de la suppression : un enfant créé entre les deux était détruit
    sans que la garde ait joué (TOCTOU). La garde appartient donc au service.
    """
    from docflow.errors import DependentsConflictError

    parent = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Parent", block_id=test_block["id"])
    )
    await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Child", parent_id=parent.doc_technical_key, block_id=test_block["id"]
        ),
    )

    with pytest.raises(DependentsConflictError) as exc:
        await doc_svc.delete_document(db_pool, _WS, parent.doc_technical_key, confirm=False)
    assert exc.value.dependents == 1
    # Refus = aucune destruction, même partielle.
    assert await doc_svc.get_document(db_pool, _WS, parent.doc_technical_key) is not None

    # Confirmé : la cascade s'applique.
    await doc_svc.delete_document(db_pool, _WS, parent.doc_technical_key, confirm=True)
    with pytest.raises(HTTPException) as http_exc:
        await doc_svc.get_document(db_pool, _WS, parent.doc_technical_key)
    assert http_exc.value.status_code == 404


async def test_delete_document_without_descendants_needs_no_confirm(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    """Sans descendant, la garde ne se déclenche pas — `confirm` reste inutile."""
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Seul", block_id=test_block["id"])
    )
    await doc_svc.delete_document(db_pool, _WS, doc.doc_technical_key, confirm=False)
    with pytest.raises(HTTPException) as exc:
        await doc_svc.get_document(db_pool, _WS, doc.doc_technical_key)
    assert exc.value.status_code == 404

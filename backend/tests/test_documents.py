from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.schemas.document import DocumentCreate, DocumentUpdate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def test_create_document(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Ma page", contenu="# Hello")
    )
    assert doc.title == "Ma page"
    assert doc.contenu == "# Hello"
    assert doc.parent_id is None
    assert doc.functional_type_slug is None
    assert doc.workspace_slug == _WS


async def test_create_document_with_type(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Epic Doc", functional_type_slug="epic")
    )
    assert doc.functional_type_slug == "epic"


async def test_create_document_unknown_type(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    with pytest.raises(HTTPException) as exc:
        await doc_svc.create_document(
            db_pool, _WS, DocumentCreate(title="Bad", functional_type_slug="ghost")
        )
    assert exc.value.status_code == 422


async def test_list_documents(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await doc_svc.create_document(db_pool, _WS, DocumentCreate(title="Page A"))
    await doc_svc.create_document(db_pool, _WS, DocumentCreate(title="Page B"))
    docs = await doc_svc.list_documents(db_pool, _WS)
    titles = [d.title for d in docs]
    assert "Page A" in titles and "Page B" in titles


async def test_document_parent_hierarchy(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    parent = await doc_svc.create_document(db_pool, _WS, DocumentCreate(title="Parent"))
    child = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Child", parent_id=parent.doc_technical_key)
    )
    assert child.parent_id == parent.doc_technical_key


async def test_document_parent_wrong_workspace(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """I-1 : parent doit être dans le même workspace."""
    from docflow.schemas.workspace import WorkspaceCreate
    from docflow.workspaces import service as ws_svc

    other_ws = await ws_svc.create_workspace(
        db_pool, WorkspaceCreate(slug="other-ws", label="Other")
    )
    parent = await doc_svc.create_document(
        db_pool, "other-ws", DocumentCreate(title="Other parent")
    )
    try:
        with pytest.raises(HTTPException) as exc:
            await doc_svc.create_document(
                db_pool, _WS, DocumentCreate(title="Child", parent_id=parent.doc_technical_key)
            )
        assert exc.value.status_code == 422
        assert "I-1" in exc.value.detail
    finally:
        await db_pool.execute(
            "DELETE FROM workspace WHERE workspace_technical_key = $1",
            other_ws.workspace_technical_key,
        )


async def test_update_document(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    doc = await doc_svc.create_document(db_pool, _WS, DocumentCreate(title="Original"))
    updated = await doc_svc.update_document(
        db_pool, _WS, doc.doc_technical_key, DocumentUpdate(title="Updated", contenu="# New")
    )
    assert updated.title == "Updated"
    assert updated.contenu == "# New"


async def test_update_document_no_changes(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    doc = await doc_svc.create_document(db_pool, _WS, DocumentCreate(title="Static"))
    result = await doc_svc.update_document(
        db_pool, _WS, doc.doc_technical_key, DocumentUpdate()
    )
    assert result.title == "Static"


async def test_get_document_not_found(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    import uuid
    with pytest.raises(HTTPException) as exc:
        await doc_svc.get_document(db_pool, _WS, uuid.uuid4())
    assert exc.value.status_code == 404


async def test_delete_document(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    doc = await doc_svc.create_document(db_pool, _WS, DocumentCreate(title="ToDelete"))
    await doc_svc.delete_document(db_pool, _WS, doc.doc_technical_key)
    with pytest.raises(HTTPException) as exc:
        await doc_svc.get_document(db_pool, _WS, doc.doc_technical_key)
    assert exc.value.status_code == 404


async def test_delete_document_with_children_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    parent = await doc_svc.create_document(db_pool, _WS, DocumentCreate(title="Parent"))
    await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Child", parent_id=parent.doc_technical_key)
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.delete_document(db_pool, _WS, parent.doc_technical_key)
    assert exc.value.status_code == 409

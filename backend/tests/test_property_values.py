from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.properties import service as prop_svc
from docflow.schemas.constraint import ConstraintCreate
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import AllowedValueCreate, PropertiesDefCreate
from docflow.schemas.property_value import PropertyValueSet
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _setup(pool: asyncpg.Pool) -> tuple[str, str]:
    """Crée type 'task' avec propriétés 'title'(text), 'count'(int), 'status'(rl)."""
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="task", label="Task"))
    await prop_svc.create_def(
        pool, _WS, "task", PropertiesDefCreate(slug="title", label="Title", type="text")
    )
    await prop_svc.create_def(
        pool, _WS, "task", PropertiesDefCreate(slug="count", label="Count", type="int")
    )
    await prop_svc.create_def(
        pool, _WS, "task",
        PropertiesDefCreate(slug="status", label="Status", type="restricted_list"),
    )
    await prop_svc.create_allowed_value(
        pool, _WS, "task", "status", AllowedValueCreate(slug="todo", label="Todo")
    )
    await prop_svc.create_allowed_value(
        pool, _WS, "task", "status", AllowedValueCreate(slug="done", label="Done", position=1)
    )
    doc = await doc_svc.create_document(
        pool, _WS, DocumentCreate(title="My task", functional_type_slug="task")
    )
    return "task", str(doc.doc_technical_key)


async def test_set_text_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    _, doc_id_str = await _setup(db_pool)
    import uuid
    doc_id = uuid.UUID(doc_id_str)
    result = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "title", PropertyValueSet(value="Hello")
    )
    assert result.value == "Hello"
    assert result.type == "text"


async def test_set_int_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    import uuid
    _, doc_id_str = await _setup(db_pool)
    doc_id = uuid.UUID(doc_id_str)
    result = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "count", PropertyValueSet(value="42")
    )
    assert result.value == "42"
    assert result.type == "int"


async def test_set_int_value_invalid(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    import uuid
    _, doc_id_str = await _setup(db_pool)
    doc_id = uuid.UUID(doc_id_str)
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "count", PropertyValueSet(value="not-an-int")
        )
    assert exc.value.status_code == 422


async def test_set_restricted_list_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    import uuid
    _, doc_id_str = await _setup(db_pool)
    doc_id = uuid.UUID(doc_id_str)
    result = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "status", PropertyValueSet(allowed_value_slug="todo")
    )
    assert result.allowed_value_slug == "todo"
    assert result.type == "restricted_list"


async def test_set_wrong_type_i3(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """I-3 : text avec allowed_value_slug → rejet."""
    import uuid
    _, doc_id_str = await _setup(db_pool)
    doc_id = uuid.UUID(doc_id_str)
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "title", PropertyValueSet(allowed_value_slug="todo")
        )
    assert exc.value.status_code == 422


async def test_i2_prop_not_in_type(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """I-2 : propriété inconnue pour ce type → rejet."""
    import uuid
    _, doc_id_str = await _setup(db_pool)
    doc_id = uuid.UUID(doc_id_str)
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "nonexistent-prop", PropertyValueSet(value="x")
        )
    assert exc.value.status_code == 422
    assert "I-2" in exc.value.detail


async def test_list_values_includes_defs(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    import uuid
    _, doc_id_str = await _setup(db_pool)
    doc_id = uuid.UUID(doc_id_str)
    await doc_svc.set_property_value(db_pool, _WS, doc_id, "title", PropertyValueSet(value="X"))
    values = await doc_svc.list_property_values(db_pool, _WS, doc_id)
    slugs = [v.prop_slug for v in values]
    assert "title" in slugs and "status" in slugs


async def test_constraint_min_max(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    import uuid
    _, doc_id_str = await _setup(db_pool)
    doc_id = uuid.UUID(doc_id_str)
    await prop_svc.upsert_constraint(
        db_pool, _WS, "task", "count", ConstraintCreate(kind="min", value="10")
    )
    await prop_svc.upsert_constraint(
        db_pool, _WS, "task", "count", ConstraintCreate(kind="max", value="100")
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "count", PropertyValueSet(value="5")
        )
    assert exc.value.status_code == 422
    ok = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "count", PropertyValueSet(value="50")
    )
    assert ok.value == "50"


async def test_constraint_pattern(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    import uuid
    _, doc_id_str = await _setup(db_pool)
    doc_id = uuid.UUID(doc_id_str)
    await prop_svc.upsert_constraint(
        db_pool, _WS, "task", "title", ConstraintCreate(kind="pattern", value=r"[A-Z].*")
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "title", PropertyValueSet(value="lowercase")
        )
    assert exc.value.status_code == 422
    ok = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "title", PropertyValueSet(value="Uppercase")
    )
    assert ok.value == "Uppercase"


async def test_constraint_pattern_only_on_text(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """I-6 : pattern interdit sur int."""
    with pytest.raises(HTTPException) as exc:
        await prop_svc.upsert_constraint(
            db_pool, _WS, "task", "count", ConstraintCreate(kind="pattern", value=r".*")
        )
    assert exc.value.status_code == 422


async def test_delete_required_value_rejected(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """I-4 : supprimer la valeur d'une propriété required → rejet."""
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="req-type", label="Req")
    )
    await prop_svc.create_def(
        db_pool, _WS, "req-type",
        PropertiesDefCreate(slug="req-prop", label="Req Prop", type="text", required=True),
    )
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Req doc", functional_type_slug="req-type")
    )
    doc_id = doc.doc_technical_key
    await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "req-prop", PropertyValueSet(value="val")
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.delete_property_value(db_pool, _WS, doc_id, "req-prop")
    assert exc.value.status_code == 422
    assert "I-4" in exc.value.detail

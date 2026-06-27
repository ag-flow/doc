from __future__ import annotations

import uuid

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


async def _setup(pool: asyncpg.Pool) -> tuple[str, uuid.UUID]:
    """Crée type 'task' avec propriétés 'title'(text), 'count'(int), 'status'(rl).

    Crée également un bloc racine 'setup-block' pour satisfaire la contrainte NOT NULL.
    """
    # Type racine pour le bloc
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
    )
    root_type_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ($1, $2, $3) RETURNING id",
        "setup-root", "Setup Root", wk,
    )
    block_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        "setup-block", "Setup Block", root_type_id, wk,
    )

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
        pool, _WS,
        DocumentCreate(title="My task", functional_type_slug="task", block_id=block_id),
    )
    return "task", doc.doc_technical_key


async def test_set_text_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    _, doc_id = await _setup(db_pool)
    result = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "title", PropertyValueSet(value="Hello", expected_version=0)
    )
    assert result.value == "Hello"
    assert result.type == "text"
    assert result.version == 1


async def test_set_int_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    _, doc_id = await _setup(db_pool)
    result = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "count", PropertyValueSet(value="42", expected_version=0)
    )
    assert result.value == "42"
    assert result.type == "int"
    assert result.version == 1


async def test_set_int_value_invalid(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    _, doc_id = await _setup(db_pool)
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "count",
            PropertyValueSet(value="not-an-int", expected_version=0)
        )
    assert exc.value.status_code == 422


async def test_set_restricted_list_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    _, doc_id = await _setup(db_pool)
    result = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "status",
        PropertyValueSet(allowed_value_slug="todo", expected_version=0)
    )
    assert result.allowed_value_slug == "todo"
    assert result.type == "restricted_list"
    assert result.version == 1


async def test_set_wrong_type_i3(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """I-3 : text avec allowed_value_slug → rejet."""
    _, doc_id = await _setup(db_pool)
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "title",
            PropertyValueSet(allowed_value_slug="todo", expected_version=0)
        )
    assert exc.value.status_code == 422


async def test_i2_prop_not_in_type(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """I-2 : propriété inconnue pour ce type → rejet."""
    _, doc_id = await _setup(db_pool)
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "nonexistent-prop",
            PropertyValueSet(value="x", expected_version=0)
        )
    assert exc.value.status_code == 422
    assert "I-2" in exc.value.detail


async def test_list_values_includes_defs(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    _, doc_id = await _setup(db_pool)
    await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "title", PropertyValueSet(value="X", expected_version=0)
    )
    values = await doc_svc.list_property_values(db_pool, _WS, doc_id)
    slugs = [v.prop_slug for v in values]
    assert "title" in slugs and "status" in slugs
    title_v = next(v for v in values if v.prop_slug == "title")
    assert title_v.version == 1
    # status jamais défini → version None
    status_v = next(v for v in values if v.prop_slug == "status")
    assert status_v.version is None


async def test_optimistic_lock_409_dod3(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """DoD 3 : écrire statut v1, rejouer avec mauvais expected_version → 409 + état courant."""
    _, doc_id = await _setup(db_pool)

    # Première écriture (v0 → v1)
    result = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "status",
        PropertyValueSet(allowed_value_slug="todo", expected_version=0)
    )
    assert result.version == 1

    # Rejouer avec expected_version=0 (devrait être 1) → 409
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "status",
            PropertyValueSet(allowed_value_slug="done", expected_version=0)
        )
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert detail["version"] == 1
    assert detail["allowed_value_slug"] == "todo"

    # Base inchangée
    values = await doc_svc.list_property_values(db_pool, _WS, doc_id)
    statut = next(v for v in values if v.prop_slug == "status")
    assert statut.version == 1
    assert statut.allowed_value_slug == "todo"


async def test_version_bump_increments(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """Chaque écriture correcte incrémente la version."""
    _, doc_id = await _setup(db_pool)
    r1 = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "title", PropertyValueSet(value="v1", expected_version=0)
    )
    assert r1.version == 1
    r2 = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "title", PropertyValueSet(value="v2", expected_version=1)
    )
    assert r2.version == 2
    values = await doc_svc.list_property_values(db_pool, _WS, doc_id)
    title_v = next(v for v in values if v.prop_slug == "title")
    assert title_v.version == 2
    assert title_v.value == "v2"


async def test_constraint_min_422_dod4(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """DoD 4 : budget_jours = -1 → 422 avec message de la contrainte min."""
    _, _ = await _setup(db_pool)
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="story", label="Story"))
    await prop_svc.create_def(
        db_pool, _WS, "story",
        PropertiesDefCreate(slug="budget_jours", label="Budget jours", type="int"),
    )
    await prop_svc.upsert_constraint(
        db_pool, _WS, "story", "budget_jours",
        ConstraintCreate(kind="min", value="0", message="budget_jours ne peut pas être négatif"),
    )
    # Réutilise le bloc créé par _setup
    block_id: uuid.UUID = await db_pool.fetchval(
        "SELECT id FROM data_block WHERE slug = $1", "setup-block"
    )
    doc = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(title="Story 1", functional_type_slug="story", block_id=block_id),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc.doc_technical_key, "budget_jours",
            PropertyValueSet(value="-1", expected_version=0)
        )
    assert exc.value.status_code == 422
    assert "budget_jours ne peut pas être négatif" in exc.value.detail


async def test_allowed_value_wrong_def_422_dod5(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 5 : restricted_list pointant une allowed_value d'une autre def → 422."""
    _, doc_id = await _setup(db_pool)
    # Ajoute une prop 'priority' avec 'high'
    await prop_svc.create_def(
        db_pool, _WS, "task",
        PropertiesDefCreate(slug="priority", label="Priority", type="restricted_list"),
    )
    await prop_svc.create_allowed_value(
        db_pool, _WS, "task", "priority",
        AllowedValueCreate(slug="high", label="High"),
    )
    # "high" appartient à "priority", pas à "status"
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "status",
            PropertyValueSet(allowed_value_slug="high", expected_version=0)
        )
    assert exc.value.status_code == 422
    assert "I-5" in exc.value.detail


async def test_constraint_min_max(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    _, doc_id = await _setup(db_pool)
    await prop_svc.upsert_constraint(
        db_pool, _WS, "task", "count", ConstraintCreate(kind="min", value="10")
    )
    await prop_svc.upsert_constraint(
        db_pool, _WS, "task", "count", ConstraintCreate(kind="max", value="100")
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "count", PropertyValueSet(value="5", expected_version=0)
        )
    assert exc.value.status_code == 422
    ok = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "count", PropertyValueSet(value="50", expected_version=0)
    )
    assert ok.value == "50"


async def test_constraint_pattern(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    _, doc_id = await _setup(db_pool)
    await prop_svc.upsert_constraint(
        db_pool, _WS, "task", "title", ConstraintCreate(kind="pattern", value=r"[A-Z].*")
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, _WS, doc_id, "title", PropertyValueSet(value="lowercase", expected_version=0)
        )
    assert exc.value.status_code == 422
    ok = await doc_svc.set_property_value(
        db_pool, _WS, doc_id, "title", PropertyValueSet(value="Uppercase", expected_version=0)
    )
    assert ok.value == "Uppercase"


async def test_constraint_pattern_only_on_text(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """I-6 : pattern interdit sur int."""
    await _setup(db_pool)
    with pytest.raises(HTTPException) as exc:
        await prop_svc.upsert_constraint(
            db_pool, _WS, "task", "count", ConstraintCreate(kind="pattern", value=r".*")
        )
    assert exc.value.status_code == 422


async def test_delete_required_value_rejected(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """I-4 : supprimer la valeur d'une propriété required → rejet."""
    _, _ = await _setup(db_pool)
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="req-type", label="Req")
    )
    await prop_svc.create_def(
        db_pool, _WS, "req-type",
        PropertiesDefCreate(slug="req-prop", label="Req Prop", type="text", required=True),
    )
    block_id: uuid.UUID = await db_pool.fetchval(
        "SELECT id FROM data_block WHERE slug = $1", "setup-block"
    )
    doc = await doc_svc.create_document(
        db_pool, _WS,
        DocumentCreate(title="Req doc", functional_type_slug="req-type", block_id=block_id),
    )
    await doc_svc.set_property_value(
        db_pool, _WS, doc.doc_technical_key, "req-prop",
        PropertyValueSet(value="val", expected_version=0)
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.delete_property_value(db_pool, _WS, doc.doc_technical_key, "req-prop")
    assert exc.value.status_code == 422
    assert "I-4" in exc.value.detail

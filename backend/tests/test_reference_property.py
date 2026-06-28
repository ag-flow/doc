"""Tests spec 38 — MREL : type de propriété 'reference'."""
from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.schemas.document import DocumentCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.schemas.properties import PropertiesDefCreate
from docflow.schemas.property_value import PropertyValueSet
from docflow.documents import service as doc_svc
from docflow.types import service as type_svc
from docflow.properties import service as prop_svc


async def test_create_reference_property_def(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="rtype1", label="R1"))
    prop = await prop_svc.create_def(
        db_pool, ws, "rtype1",
        PropertiesDefCreate(slug="ref-field", label="Réf", type="reference"),
    )
    assert prop.type == "reference"
    assert prop.target_functional_type_slug is None


async def test_set_reference_property_value(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="rtype2", label="R2"))
    await prop_svc.create_def(
        db_pool, ws, "rtype2",
        PropertiesDefCreate(slug="ref-v", label="Réf V", type="reference"),
    )
    doc_src = await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(title="Source", parent_id=None, functional_type_slug="rtype2"),
    )
    doc_tgt = await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(title="Cible", parent_id=None, functional_type_slug="rtype2"),
    )
    src_id = doc_src.doc_technical_key
    tgt_id = str(doc_tgt.doc_technical_key)
    result = await doc_svc.set_property_value(
        db_pool, ws, src_id, "ref-v",
        PropertyValueSet(value=tgt_id, expected_version=0),
    )
    assert result.value == tgt_id
    assert result.type == "reference"


async def test_reference_invalid_uuid(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="rtype3", label="R3"))
    await prop_svc.create_def(
        db_pool, ws, "rtype3",
        PropertiesDefCreate(slug="ref-bad", label="Réf bad", type="reference"),
    )
    doc_src = await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(title="Src", parent_id=None, functional_type_slug="rtype3"),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, ws, doc_src.doc_technical_key, "ref-bad",
            PropertyValueSet(value="not-a-uuid", expected_version=0),
        )
    assert exc.value.status_code == 422


async def test_reference_doc_not_in_workspace(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    import uuid
    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="rtype4", label="R4"))
    await prop_svc.create_def(
        db_pool, ws, "rtype4",
        PropertiesDefCreate(slug="ref-nf", label="Réf NF", type="reference"),
    )
    doc_src = await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(title="SrcNF", parent_id=None, functional_type_slug="rtype4"),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, ws, doc_src.doc_technical_key, "ref-nf",
            PropertyValueSet(value=str(uuid.uuid4()), expected_version=0),
        )
    assert exc.value.status_code == 422
    assert "introuvable dans ce workspace" in exc.value.detail


async def test_reference_target_type_constraint(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="tsrc5", label="Src"))
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="ttgt5", label="Tgt"))

    await prop_svc.create_def(
        db_pool, ws, "tsrc5",
        PropertiesDefCreate(
            slug="ref-constrained",
            label="Réf contrainte",
            type="reference",
            target_functional_type_slug="ttgt5",
        ),
    )
    doc_src = await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(title="Src5", parent_id=None, functional_type_slug="tsrc5"),
    )
    doc_right = await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(title="Bon type", parent_id=None, functional_type_slug="ttgt5"),
    )
    doc_wrong = await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(title="Mauvais type", parent_id=None, functional_type_slug="tsrc5"),
    )
    src_id = doc_src.doc_technical_key

    # Bon type → OK
    result = await doc_svc.set_property_value(
        db_pool, ws, src_id, "ref-constrained",
        PropertyValueSet(value=str(doc_right.doc_technical_key), expected_version=0),
    )
    assert result.value == str(doc_right.doc_technical_key)

    # Mauvais type → rejet
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool, ws, src_id, "ref-constrained",
            PropertyValueSet(value=str(doc_wrong.doc_technical_key), expected_version=1),
        )
    assert exc.value.status_code == 422
    assert "type fonctionnel" in exc.value.detail


async def test_target_functional_type_only_for_reference(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="tnref", label="Nonref"))
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_def(
            db_pool, ws, "tnref",
            PropertiesDefCreate(
                slug="tf",
                label="Champ texte",
                type="text",
                target_functional_type_slug="tnref",
            ),
        )
    assert exc.value.status_code == 422

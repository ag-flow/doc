"""Contrat dur des propriétés : required contraignant + behaviors automatiques."""

from __future__ import annotations

import datetime
from typing import Any

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.schemas.document import DocumentCreate, DocumentUpdate
from docflow.schemas.properties import PropertiesDefCreate
from docflow.schemas.property_value import PropertyValueSet

_WS = "test-ws"
_TODAY = datetime.date.today().isoformat()


@pytest.fixture()
async def contract_type(db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict) -> Any:
    """Ajoute au type du bloc : statut (required, restricted_list), revision (auto_now)."""
    from docflow.properties import service as prop_svc
    from docflow.schemas.properties import AllowedValueCreate

    await prop_svc.create_def(
        db_pool,
        _WS,
        "root-type",
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list", required=True),
    )
    await prop_svc.create_allowed_value(
        db_pool, _WS, "root-type", "statut", AllowedValueCreate(slug="a-faire", label="À faire")
    )
    await prop_svc.create_def(
        db_pool,
        _WS,
        "root-type",
        PropertiesDefCreate(
            slug="revision", label="Dernière révision", type="date", behavior="auto_now"
        ),
    )
    return test_block


async def _get_value(db_pool: asyncpg.Pool, doc_id: Any, prop_slug: str) -> str | None:
    vals = await doc_svc.list_property_values(db_pool, _WS, doc_id)
    for v in vals:
        if v.prop_slug == prop_slug:
            return v.allowed_value_slug or v.value
    return None


async def test_create_sans_required_refuse(db_pool: asyncpg.Pool, contract_type: dict) -> None:
    """Création sans les required → 422 listant les slugs manquants."""
    with pytest.raises(HTTPException) as exc:
        await doc_svc.create_document(
            db_pool,
            _WS,
            DocumentCreate(
                title="Incomplet",
                block_id=contract_type["id"],
                functional_type_slug="root-type",
            ),
        )
    assert exc.value.status_code == 422
    assert "propriétés obligatoires non renseignées : statut" in str(exc.value.detail)


async def test_create_avec_properties_ok_et_auto_now(
    db_pool: asyncpg.Pool, contract_type: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Complet",
            block_id=contract_type["id"],
            functional_type_slug="root-type",
            properties={"statut": "a-faire"},
        ),
    )
    assert await _get_value(db_pool, doc.doc_technical_key, "statut") == "a-faire"
    # behavior auto_now posé par le serveur à la création
    assert await _get_value(db_pool, doc.doc_technical_key, "revision") == _TODAY


async def test_ecriture_manuelle_behavior_refusee(
    db_pool: asyncpg.Pool, contract_type: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Auto",
            block_id=contract_type["id"],
            functional_type_slug="root-type",
            properties={"statut": "a-faire"},
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.set_property_value(
            db_pool,
            _WS,
            doc.doc_technical_key,
            "revision",
            PropertyValueSet(value="2020-01-01", expected_version=1),
        )
    assert exc.value.status_code == 422
    assert "gérée automatiquement" in str(exc.value.detail)
    # ... y compris dans properties à la création
    with pytest.raises(HTTPException) as exc2:
        await doc_svc.create_document(
            db_pool,
            _WS,
            DocumentCreate(
                title="Auto2",
                block_id=contract_type["id"],
                functional_type_slug="root-type",
                properties={"statut": "a-faire", "revision": "2020-01-01"},
            ),
        )
    assert "gérée automatiquement" in str(exc2.value.detail)


async def test_auto_now_repose_a_chaque_enregistrement(
    db_pool: asyncpg.Pool, contract_type: dict
) -> None:
    """Contenu, valeur de prop : chaque enregistrement bump la version de revision."""
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Rev",
            block_id=contract_type["id"],
            functional_type_slug="root-type",
            properties={"statut": "a-faire"},
        ),
    )

    async def _rev_version() -> int | None:
        vals = await doc_svc.list_property_values(db_pool, _WS, doc.doc_technical_key)
        return next(v.version for v in vals if v.prop_slug == "revision")

    v0 = await _rev_version()
    assert v0 == 1  # posée à la création
    # Sauvegarde de contenu → révision reposée
    await doc_svc.update_document(
        db_pool,
        _WS,
        doc.doc_technical_key,
        DocumentUpdate(content="# maj", expected_version=1),
    )
    assert await _rev_version() == v0 + 1
    # Set d'une autre propriété → révision reposée aussi (décision : tout
    # enregistrement vaut révision)
    await doc_svc.set_property_value(
        db_pool,
        _WS,
        doc.doc_technical_key,
        "statut",
        PropertyValueSet(allowed_value_slug="a-faire", expected_version=1),
    )
    assert await _rev_version() == v0 + 2


async def test_required_avec_default_ne_bloque_pas(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    from docflow.properties import service as prop_svc

    await prop_svc.create_def(
        db_pool,
        _WS,
        "root-type",
        PropertiesDefCreate(
            slug="prio", label="Priorité", type="text", required=True, default_value="normale"
        ),
    )
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Défaut suffit", block_id=test_block["id"], functional_type_slug="root-type"
        ),
    )
    assert doc.title == "Défaut suffit"


async def test_behavior_reserve_au_type_date() -> None:
    with pytest.raises(ValueError, match="réservé aux propriétés de type 'date'"):
        PropertiesDefCreate(slug="bad", label="Bad", type="text", behavior="auto_now")

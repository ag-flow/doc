from __future__ import annotations

import uuid

import asyncpg
import pytest
import structlog
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.properties import service as prop_svc
from docflow.schemas.constraint import ConstraintCreate
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import PropertiesDefCreate
from docflow.schemas.property_value import PropertyValueSet
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"
_TYPE = "task"

_PROPS: tuple[tuple[str, str], ...] = (
    ("count", "int"),
    ("ratio", "float"),
    ("due", "date"),
    ("title", "text"),
)


async def _setup(pool: asyncpg.Pool) -> uuid.UUID:
    """Crée le type 'task' (une propriété par type scalaire) et un document vierge."""
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
    )
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug=_TYPE, label="Task"))
    type_id: uuid.UUID = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        _TYPE,
    )
    block_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        "constraints-block",
        "Constraints Block",
        type_id,
        wk,
    )
    for slug, ptype in _PROPS:
        await prop_svc.create_def(
            pool,
            _WS,
            _TYPE,
            PropertiesDefCreate(slug=slug, label=slug, type=ptype),  # type: ignore[arg-type]
        )
    doc = await doc_svc.create_document(
        pool,
        _WS,
        DocumentCreate(title="Doc", functional_type_slug=_TYPE, block_id=block_id),
    )
    return doc.doc_technical_key


async def _inject_raw_constraint(pool: asyncpg.Pool, prop_slug: str, kind: str, value: str) -> None:
    """Injecte une contrainte SANS validation, comme une donnée héritée en base."""
    await pool.execute(
        "INSERT INTO properties_constraints (property_def_ref, kind, value) "
        "SELECT pd.id, $2, $3 FROM properties_defs pd "
        "JOIN functional_type ft ON ft.id = pd.functional_type_ref "
        "JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key "
        "WHERE w.slug = $4 AND ft.slug = $5 AND pd.slug = $1",
        prop_slug,
        kind,
        value,
        _WS,
        _TYPE,
    )


# ── Rejet de l'opérande invalide à l'écriture de la contrainte ────────────────


@pytest.mark.parametrize(
    ("prop_slug", "kind", "value"),
    [
        ("count", "min", "dix"),
        ("count", "max", "10.5"),
        ("ratio", "min", "beaucoup"),
        ("due", "min", "2026-13-01"),
        ("due", "max", "hier"),
        ("title", "min_length", "trois"),
        ("title", "max_length", "-1"),
        ("title", "min_length", "2.5"),
        ("title", "pattern", "(["),
    ],
)
async def test_operande_invalide_refusee_422(
    db_pool: asyncpg.Pool, test_workspace: dict, prop_slug: str, kind: str, value: str
) -> None:
    """Une contrainte dont l'opérande est inexploitable est refusée à l'écriture.

    Sans ce contrôle elle est acceptée puis soit inerte (elle ne protège rien),
    soit fatale (500 à chaque écriture de la propriété).
    """
    await _setup(db_pool)
    with pytest.raises(HTTPException) as exc:
        await prop_svc.upsert_constraint(
            db_pool,
            _WS,
            _TYPE,
            prop_slug,
            ConstraintCreate(kind=kind, value=value),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 422
    assert kind in str(exc.value.detail)
    stored = await prop_svc.list_constraints(db_pool, _WS, _TYPE, prop_slug)
    assert stored == []


@pytest.mark.parametrize(
    ("prop_slug", "kind", "value"),
    [
        ("count", "min", "0"),
        ("count", "max", "100"),
        ("ratio", "min", "-1.5"),
        ("due", "max", "2026-12-31"),
        ("title", "min_length", "0"),
        ("title", "max_length", "12"),
        ("title", "pattern", "[A-Z].*"),
    ],
)
async def test_operande_valide_acceptee(
    db_pool: asyncpg.Pool, test_workspace: dict, prop_slug: str, kind: str, value: str
) -> None:
    await _setup(db_pool)
    out = await prop_svc.upsert_constraint(
        db_pool,
        _WS,
        _TYPE,
        prop_slug,
        ConstraintCreate(kind=kind, value=value),  # type: ignore[arg-type]
    )
    assert out.value == value


# ── Contrainte héritée invalide : ni 500, ni silence ─────────────────────────


@pytest.mark.parametrize(
    ("prop_slug", "kind", "operand", "value"),
    [
        ("count", "min", "dix", "5"),
        ("ratio", "max", "beaucoup", "5.5"),
        ("due", "min", "hier", "2026-01-01"),
        ("title", "min_length", "trois", "ab"),
        ("title", "max_length", "-1", "abcdef"),
        ("title", "pattern", "([", "quoi que ce soit"),
    ],
)
async def test_operande_heritee_invalide_ignoree_et_tracee(
    db_pool: asyncpg.Pool, test_workspace: dict, prop_slug: str, kind: str, operand: str, value: str
) -> None:
    """Une contrainte déjà en base avec un opérande cassé n'arrête pas l'écriture…

    …mais elle laisse une trace : sinon la contrainte est inerte sans que personne
    ne le sache. Avant durcissement : 500 (min_length/max_length/pattern) ou
    silence total (min/max).
    """
    doc_id = await _setup(db_pool)
    await _inject_raw_constraint(db_pool, prop_slug, kind, operand)

    with structlog.testing.capture_logs() as logs:
        written = await doc_svc.set_property_value(
            db_pool, _WS, doc_id, prop_slug, PropertyValueSet(value=value, expected_version=0)
        )
    assert written.value == value
    skipped = [entry for entry in logs if entry["event"] == "constraint_operand_invalid_skipped"]
    assert len(skipped) == 1
    assert skipped[0]["kind"] == kind
    assert skipped[0]["operand"] == operand


async def test_contrainte_valide_rejette_toujours(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Non-régression : les contraintes exploitables continuent de rejeter."""
    doc_id = await _setup(db_pool)
    for prop_slug, kind, operand, bad in (
        ("count", "min", "10", "5"),
        ("ratio", "max", "1.5", "2.5"),
        ("due", "min", "2026-06-01", "2026-01-01"),
        ("title", "max_length", "3", "abcdef"),
    ):
        await prop_svc.upsert_constraint(
            db_pool,
            _WS,
            _TYPE,
            prop_slug,
            ConstraintCreate(kind=kind, value=operand),  # type: ignore[arg-type]
        )
        with pytest.raises(HTTPException) as exc:
            await doc_svc.set_property_value(
                db_pool, _WS, doc_id, prop_slug, PropertyValueSet(value=bad, expected_version=0)
            )
        assert exc.value.status_code == 422

"""Tests MPTS — types scalaires date, bool, url, float (spec 34)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from docflow.documents.service import (
    _validate_bool,
    _validate_date,
    _validate_float,
    _validate_url,
)


# ── Validateurs unitaires (sans DB) ──────────────────────────────────────────

def test_date_valid() -> None:
    _validate_date("2026-09-15", "date-prop")  # ne lève pas


def test_date_invalid_format() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_date("15/09/2026", "date-prop")
    assert exc.value.status_code == 422


def test_date_invalid_garbage() -> None:
    with pytest.raises(HTTPException):
        _validate_date("abc", "date-prop")


def test_bool_true() -> None:
    _validate_bool("true", "bool-prop")


def test_bool_false() -> None:
    _validate_bool("false", "bool-prop")


def test_bool_invalid_yes() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_bool("oui", "bool-prop")
    assert exc.value.status_code == 422
    assert "oui" in exc.value.detail


def test_bool_invalid_one() -> None:
    with pytest.raises(HTTPException):
        _validate_bool("1", "bool-prop")


def test_url_valid_https() -> None:
    _validate_url("https://figma.com/design/123", "url-prop")


def test_url_valid_http() -> None:
    _validate_url("http://example.com", "url-prop")


def test_url_invalid_no_scheme() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_url("figma.com/design", "url-prop")
    assert exc.value.status_code == 422


def test_url_invalid_ftp_scheme() -> None:
    with pytest.raises(HTTPException):
        _validate_url("ftp://example.com", "url-prop")


def test_float_valid() -> None:
    _validate_float("3.14", "float-prop")
    _validate_float("-3.14", "float-prop")
    _validate_float("0", "float-prop")


def test_float_invalid() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_float("abc", "float-prop")
    assert exc.value.status_code == 422


# ── Contraintes min/max sur DB ────────────────────────────────────────────────

async def test_constraint_min_max_float(db_pool, test_workspace: dict) -> None:
    from docflow.schemas.types import FunctionalTypeCreate
    from docflow.schemas.properties import PropertiesDefCreate
    from docflow.schemas.constraint import ConstraintCreate
    from docflow.types import service as type_svc
    from docflow.properties import service as prop_svc

    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="t34f", label="T34F"))
    await prop_svc.create_def(
        db_pool, ws, "t34f",
        PropertiesDefCreate(slug="charge", label="Charge", type="float"),
    )
    c = await prop_svc.upsert_constraint(
        db_pool, ws, "t34f", "charge", ConstraintCreate(kind="min", value="1.0"),
    )
    assert c.kind == "min"


async def test_constraint_pattern_rejected_on_float(db_pool, test_workspace: dict) -> None:
    from docflow.schemas.types import FunctionalTypeCreate
    from docflow.schemas.properties import PropertiesDefCreate
    from docflow.schemas.constraint import ConstraintCreate
    from docflow.types import service as type_svc
    from docflow.properties import service as prop_svc

    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="t34r", label="T34R"))
    await prop_svc.create_def(
        db_pool, ws, "t34r",
        PropertiesDefCreate(slug="charge2", label="Charge2", type="float"),
    )
    with pytest.raises(HTTPException) as exc:
        await prop_svc.upsert_constraint(
            db_pool, ws, "t34r", "charge2", ConstraintCreate(kind="pattern", value=".*"),
        )
    assert exc.value.status_code == 422


async def test_constraint_min_max_date(db_pool, test_workspace: dict) -> None:
    from docflow.schemas.types import FunctionalTypeCreate
    from docflow.schemas.properties import PropertiesDefCreate
    from docflow.schemas.constraint import ConstraintCreate
    from docflow.types import service as type_svc
    from docflow.properties import service as prop_svc

    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="t34d", label="T34D"))
    await prop_svc.create_def(
        db_pool, ws, "t34d",
        PropertiesDefCreate(slug="echeance", label="Échéance", type="date"),
    )
    c = await prop_svc.upsert_constraint(
        db_pool, ws, "t34d", "echeance", ConstraintCreate(kind="min", value="2026-01-01"),
    )
    assert c.kind == "min"

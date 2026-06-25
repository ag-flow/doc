from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from docflow.app import app
from docflow.auth.jwt import create_token
from docflow.schemas.auth import AuthUser
from docflow.schemas.types import FunctionalTypeCreate, FunctionalTypeUpdate
from docflow.types import service as type_svc

_JWT_SECRET = "test_jwt_secret_for_m2"
_BOOTSTRAP_EMAIL = "bootstrap@example.com"
_BOOTSTRAP_PW = "bootstrap_pw_123"
_BASE_ENV = {
    "ADMIN_EMAIL": _BOOTSTRAP_EMAIL,
    "ADMIN_PASSWORD": _BOOTSTRAP_PW,
    "JWT_SECRET": _JWT_SECRET,
}
_WS = "test-ws"


def _admin_token(user_id: uuid.UUID) -> str:
    user = AuthUser(id=user_id, email="a@b.com", label="L", is_superadmin=True, disabled=False)
    return create_token(user, _JWT_SECRET)


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    return TestClient(app)


# ── Service-layer tests ───────────────────────────────────────────────────────


async def test_create_type(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    out = await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    assert out.slug == "epic"
    assert out.parent_slug is None
    assert out.workspace_slug == _WS


async def test_type_slug_unique_per_workspace(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    with pytest.raises(HTTPException) as exc:
        await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic2"))
    assert exc.value.status_code == 409


async def test_list_types(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="feature", label="Feature"))
    types = await type_svc.list_types(db_pool, _WS)
    slugs = [t.slug for t in types]
    assert "epic" in slugs and "feature" in slugs


async def test_parent_hierarchy(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    child = await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="feature", label="Feature", parent_slug="epic")
    )
    assert child.parent_slug == "epic"


async def test_parent_must_be_same_workspace(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    with pytest.raises(HTTPException) as exc:
        await type_svc.create_type(
            db_pool,
            _WS,
            FunctionalTypeCreate(slug="feature", label="Feature", parent_slug="nonexistent"),
        )
    assert exc.value.status_code == 422


async def test_cycle_detection(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="a", label="A"))
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="b", label="B", parent_slug="a")
    )
    with pytest.raises(HTTPException) as exc:
        await type_svc.update_type(db_pool, _WS, "a", FunctionalTypeUpdate(parent_slug="b"))
    assert exc.value.status_code == 422


async def test_delete_type_with_children_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="feature", label="Feature", parent_slug="epic")
    )
    with pytest.raises(HTTPException) as exc:
        await type_svc.delete_type(db_pool, _WS, "epic")
    assert exc.value.status_code == 409


async def test_delete_type_ok(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="leaf", label="Leaf"))
    await type_svc.delete_type(db_pool, _WS, "leaf")
    types = await type_svc.list_types(db_pool, _WS)
    assert not any(t.slug == "leaf" for t in types)


async def test_update_type_label(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    updated = await type_svc.update_type(
        db_pool, _WS, "epic", FunctionalTypeUpdate(label="Epic (renamed)")
    )
    assert updated.label == "Epic (renamed)"


async def test_slug_invalid_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FunctionalTypeCreate(slug="UPPERCASE", label="Bad")


# ── Router-level auth tests ───────────────────────────────────────────────────


def test_unauthenticated_types_rejected(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        resp = client.get(f"/workspaces/{_WS}/types")
    assert resp.status_code == 401


async def test_types_crud_via_http(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
    test_workspace: dict,
) -> None:
    """Test HTTP round-trip : login → CRUD types (workspace fourni par test_workspace)."""
    with _client(monkeypatch, test_schema_url) as client:
        login = client.post(
            "/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
        token = login.json()["access_token"]
        hdrs = {"Authorization": f"Bearer {token}"}

        r = client.post(
            f"/workspaces/{_WS}/types",
            json={"slug": "http-epic", "label": "HTTP Epic"},
            headers=hdrs,
        )
        assert r.status_code == 201
        assert r.json()["slug"] == "http-epic"

        r = client.get(f"/workspaces/{_WS}/types", headers=hdrs)
        assert r.status_code == 200
        assert "http-epic" in [t["slug"] for t in r.json()]

        r = client.delete(f"/workspaces/{_WS}/types/http-epic", headers=hdrs)
        assert r.status_code == 204

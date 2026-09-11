"""Escalade de privilège : seul un superadmin crée un profil de clé API admin.

Un profil `is_admin=true` produit une clé « sans restriction » (check_api_key_scope
et _check_tool_authz deviennent no-op) : le poser doit exiger le rôle superadmin,
sur la surface REST comme dans le service.
"""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from docflow.apikeys import service as svc
from docflow.apikeys.schemas import ApiProfileCreate, ApiProfileUpdate
from docflow.app import app

_JWT_SECRET = "test_jwt_apikeys_authz"
_ADMIN = "akauthz-admin@example.com"
_USER = "akauthz-user@example.com"
_PW = "akauthz_pw_123456"


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    return TestClient(app)


def _login(client: TestClient, email: str) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"email": email, "password": _PW})
    assert login.status_code == 200, login.text
    token = client.cookies.get("docflow_session")
    client.cookies.clear()
    return {"docflow_session": token}


def _setup_users(client: TestClient, test_schema_url: str) -> tuple[dict[str, str], dict[str, str]]:
    """(headers superadmin, headers utilisateur validé non-admin)."""
    client.post(
        "/api/setup/init-admin",
        json={"username": "akauthzadmin", "email": _ADMIN, "password": _PW},
    )
    admin = _login(client, _ADMIN)
    r = client.post(
        "/api/admin/users",
        json={"email": _USER, "label": "AK Authz User", "password": _PW},
        cookies=admin,
    )
    assert r.status_code in (200, 201), r.text

    async def _validate() -> None:
        conn = await asyncpg.connect(test_schema_url)
        try:
            await conn.execute(
                "UPDATE app_user SET validated = true, disabled = false, is_admin = false "
                "WHERE email = $1",
                _USER,
            )
        finally:
            await conn.close()

    asyncio.run(_validate())
    return admin, _login(client, _USER)


def test_non_admin_ne_peut_pas_creer_profil_admin(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        _, user = _setup_users(client, test_schema_url)
        r = client.post(
            "/api/user/api-profiles",
            json={"name": "escalade", "is_admin": True},
            cookies=user,
        )
        assert r.status_code == 403, r.text


def test_non_admin_ne_peut_pas_promouvoir_profil(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        _, user = _setup_users(client, test_schema_url)
        created = client.post(
            "/api/user/api-profiles", json={"name": "normal-puis-admin"}, cookies=user
        )
        assert created.status_code == 201, created.text
        pid = created.json()["id"]

        r = client.patch(f"/api/user/api-profiles/{pid}", json={"is_admin": True}, cookies=user)
        assert r.status_code == 403, r.text

        detail = client.get(f"/api/user/api-profiles/{pid}", cookies=user)
        assert detail.json()["is_admin"] is False


def test_non_admin_profil_normal_reste_autorise(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    """Non-régression : le cas nominal (profil non-admin) n'est pas cassé."""
    with _client(monkeypatch, test_schema_url) as client:
        _, user = _setup_users(client, test_schema_url)
        created = client.post("/api/user/api-profiles", json={"name": "nominal"}, cookies=user)
        assert created.status_code == 201, created.text
        assert created.json()["is_admin"] is False
        pid = created.json()["id"]

        renamed = client.patch(
            f"/api/user/api-profiles/{pid}", json={"name": "nominal-2"}, cookies=user
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "nominal-2"


def test_superadmin_peut_creer_profil_admin(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        admin, _ = _setup_users(client, test_schema_url)
        r = client.post(
            "/api/user/api-profiles",
            json={"name": "profil-admin", "is_admin": True},
            cookies=admin,
        )
        assert r.status_code == 201, r.text
        assert r.json()["is_admin"] is True


# ── Service : la règle vaut quel que soit l'appelant (défaut fail-closed) ─────


@pytest.fixture()
async def owner(db_pool: asyncpg.Pool) -> uuid.UUID:
    row = await db_pool.fetchrow(
        "INSERT INTO app_user (email, label, password_hash, is_admin, validated, source) "
        "VALUES ($1, $2, $3, false, true, 'local') RETURNING id",
        "akauthz-owner@test.local",
        "AK Authz Owner",
        "x",
    )
    assert row is not None
    oid: uuid.UUID = row["id"]
    yield oid
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", oid)


async def test_service_create_refuse_admin_par_defaut(
    db_pool: asyncpg.Pool, owner: uuid.UUID
) -> None:
    with pytest.raises(HTTPException) as exc:
        await svc.create_profile(db_pool, owner, ApiProfileCreate(name="svc-esc", is_admin=True))
    assert exc.value.status_code == 403


async def test_service_update_champ_absent_ne_bloque_pas_profil_admin(
    db_pool: asyncpg.Pool, owner: uuid.UUID
) -> None:
    """`is_admin` absent du body ≠ `is_admin=false` : un profil déjà admin reste
    modifiable sur ses autres champs par son propriétaire non-superadmin."""
    p = await svc.create_profile(
        db_pool,
        owner,
        ApiProfileCreate(name="svc-deja-admin", is_admin=True),
        caller_is_superadmin=True,
    )
    updated = await svc.update_profile(
        db_pool, owner, p.id, ApiProfileUpdate(description="renommage")
    )
    assert updated.is_admin is True
    assert updated.description == "renommage"


async def test_service_update_retrogradation_autorisee(
    db_pool: asyncpg.Pool, owner: uuid.UUID
) -> None:
    """Retirer le drapeau admin est une réduction de privilège : toujours permis."""
    p = await svc.create_profile(
        db_pool,
        owner,
        ApiProfileCreate(name="svc-retrograde", is_admin=True),
        caller_is_superadmin=True,
    )
    updated = await svc.update_profile(db_pool, owner, p.id, ApiProfileUpdate(is_admin=False))
    assert updated.is_admin is False

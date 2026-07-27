"""Page « Mon profil » : email (matching OIDC) + GUID d'identité (OBO v6)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from docflow.app import app

_JWT_SECRET = "test_jwt_me_profile"
_EMAIL = "me@example.com"
_PW = "me_pw_123456"


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    client.post(
        "/api/setup/init-admin",
        json={"username": "me", "email": _EMAIL, "password": _PW},
    )
    login = client.post("/api/auth/login", json={"email": _EMAIL, "password": _PW})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_profile_requires_auth(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        assert client.get("/api/me/profile").status_code == 401


def test_get_and_update_profile(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)

        r = client.get("/api/me/profile", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["email"] == _EMAIL
        assert r.json()["identity"] is None

        # Pose un GUID (forme canonique renvoyée) + change l'email.
        guid = str(uuid.uuid4())
        r = client.patch(
            "/api/me/profile",
            json={"email": "Nouveau@Example.com", "identity": guid.upper()},
            headers=hdrs,
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "nouveau@example.com"  # normalisé
        assert r.json()["identity"] == guid                 # canonique

        # Effacer le GUID avec "".
        r = client.patch("/api/me/profile", json={"identity": ""}, headers=hdrs)
        assert r.status_code == 200
        assert r.json()["identity"] is None


def test_profile_validation_and_conflicts(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)

        # Formats invalides → 422.
        bad_email = client.patch("/api/me/profile", json={"email": "pas-un-email"}, headers=hdrs)
        assert bad_email.status_code == 422
        bad_guid = client.patch("/api/me/profile", json={"identity": "pas-un-guid"}, headers=hdrs)
        assert bad_guid.status_code == 422

        # Conflits d'unicité → 409.
        guid = str(uuid.uuid4())
        client.post(
            "/api/admin/users",
            json={"email": "autre@example.com", "label": "Autre", "password": "xx_pw_123456"},
            headers=hdrs,
        )
        # Pose le GUID sur l'autre compte directement en base (droits admin non requis ici).
        import asyncio

        import asyncpg

        async def _set() -> None:
            conn = await asyncpg.connect(test_schema_url)
            try:
                await conn.execute(
                    "UPDATE app_user SET identity = $1 WHERE email = 'autre@example.com'", guid
                )
            finally:
                await conn.close()

        asyncio.run(_set())
        dup = client.patch("/api/me/profile", json={"identity": guid}, headers=hdrs)
        assert dup.status_code == 409
        assert client.patch(
            "/api/me/profile", json={"email": "autre@example.com"}, headers=hdrs
        ).status_code == 409

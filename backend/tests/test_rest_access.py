"""ATDD — Contrôle d'accès par utilisateur sur la surface REST (fiche 27deaa2e).

Un utilisateur (JWT) non-membre : le workspace n'apparaît pas dans la liste et
ses ressources répondent 404 (fail closed). Un membre accède ; un superadmin
voit tout. Les requêtes par clé API restent gouvernées par leurs scopes.
"""

from __future__ import annotations

import asyncio

import asyncpg
import pytest
from fastapi.testclient import TestClient

from docflow.app import app

_JWT_SECRET = "test_jwt_rest_access"
_ADMIN = "rest-admin@example.com"
_USER = "rest-user@example.com"
_PW = "rest_pw_123456"
_WS = "rest-acl-ws"


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    return TestClient(app)


def _login(client: TestClient, email: str) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"email": email, "password": _PW})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _setup_users_and_ws(client: TestClient, test_schema_url: str) -> dict[str, str]:
    """Admin bootstrap + utilisateur simple validé + workspace créé par l'admin."""
    client.post(
        "/api/setup/init-admin",
        json={"username": "restadmin", "email": _ADMIN, "password": _PW},
    )
    admin = _login(client, _ADMIN)
    client.post(
        "/api/admin/users",
        json={"email": _USER, "label": "Rest User", "password": _PW},
        headers=admin,
    )

    async def _fix() -> None:
        conn = await asyncpg.connect(test_schema_url)
        try:
            await conn.execute(
                "UPDATE app_user SET validated = true, disabled = false WHERE email = $1", _USER
            )
        finally:
            await conn.close()

    asyncio.run(_fix())
    r = client.post("/api/workspaces", json={"slug": _WS, "label": "ACL WS"}, headers=admin)
    assert r.status_code == 201, r.text
    return admin


def test_rest_access_member_vs_non_member(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        admin = _setup_users_and_ws(client, test_schema_url)
        user = _login(client, _USER)

        # Superadmin : accès complet, liste complète.
        assert client.get(f"/api/workspaces/{_WS}/blocks", headers=admin).status_code == 200
        assert any(
            w["slug"] == _WS for w in client.get("/api/workspaces", headers=admin).json()
        )

        # Non-membre : le workspace est INVISIBLE (liste) et 404 (ressources).
        assert not any(
            w["slug"] == _WS for w in client.get("/api/workspaces", headers=user).json()
        )
        assert client.get(f"/api/workspaces/{_WS}/blocks", headers=user).status_code == 404
        assert client.get(f"/api/workspaces/{_WS}/types", headers=user).status_code == 404
        assert client.get(f"/api/workspaces/{_WS}/automations", headers=user).status_code == 404
        assert client.get(f"/api/workspaces/{_WS}/datasets", headers=user).status_code == 404
        assert client.get(f"/api/workspaces/{_WS}", headers=user).status_code == 404

        # Devenu MEMBRE : accès complet + visible dans la liste.
        async def _add_member() -> None:
            conn = await asyncpg.connect(test_schema_url)
            try:
                await conn.execute(
                    "INSERT INTO workspace_member (workspace_technical_key, user_id) "
                    "SELECT w.workspace_technical_key, u.id FROM workspace w, app_user u "
                    "WHERE w.slug = $1 AND u.email = $2 ON CONFLICT DO NOTHING",
                    _WS,
                    _USER,
                )
            finally:
                await conn.close()

        asyncio.run(_add_member())
        assert client.get(f"/api/workspaces/{_WS}/blocks", headers=user).status_code == 200
        assert client.get(f"/api/workspaces/{_WS}", headers=user).status_code == 200
        assert any(
            w["slug"] == _WS for w in client.get("/api/workspaces", headers=user).json()
        )


def test_rest_access_unknown_ws_keeps_usual_404(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        _setup_users_and_ws(client, test_schema_url)
        user = _login(client, _USER)
        # Workspace inexistant : 404 habituel (aucune fuite de différenciation).
        assert client.get("/api/workspaces/nope-ws/blocks", headers=user).status_code == 404

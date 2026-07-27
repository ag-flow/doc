"""Invitation par lien à usage unique (écart n°7)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from docflow.app import app

_JWT_SECRET = "test_jwt_invite"
_ADMIN = "invite-admin@example.com"
_PW = "invite_pw_123456"


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    return TestClient(app)


def _admin(client: TestClient) -> dict[str, str]:
    client.post(
        "/api/setup/init-admin",
        json={"username": "inviter", "email": _ADMIN, "password": _PW},
    )
    login = client.post("/api/auth/login", json={"email": _ADMIN, "password": _PW})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_invitation_full_flow(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        admin = _admin(client)

        r = client.post(
            "/api/admin/users/invite",
            json={"email": "nouvelle@example.com", "label": "Nouvelle Venue"},
            headers=admin,
        )
        assert r.status_code == 201, r.text
        path = r.json()["invite_path"]
        assert path.startswith("/invite/")
        token = path.removeprefix("/invite/")

        # Public : l'invitation dit qui est invité.
        info = client.get(f"/api/invite/{token}")
        assert info.status_code == 200
        assert info.json() == {"email": "nouvelle@example.com", "label": "Nouvelle Venue"}

        # Mot de passe trop court : refusé.
        assert client.post(f"/api/invite/{token}", json={"password": "court"}).status_code == 422

        # Acceptation : le compte devient connectable.
        assert client.post(
            f"/api/invite/{token}", json={"password": "mot-de-passe-solide"}
        ).status_code == 204
        login = client.post(
            "/api/auth/login",
            json={"email": "nouvelle@example.com", "password": "mot-de-passe-solide"},
        )
        assert login.status_code == 200

        # Usage unique : rejouer le même jeton échoue.
        assert client.get(f"/api/invite/{token}").status_code == 404
        assert client.post(
            f"/api/invite/{token}", json={"password": "autre-mot-de-passe"}
        ).status_code == 404


def test_invitation_guards(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        admin = _admin(client)
        # Jeton inconnu → même 404 (pas d'oracle).
        assert client.get("/api/invite/jeton-inconnu-mais-bien-forme-123").status_code == 404
        # Email déjà pris → 409.
        assert client.post(
            "/api/admin/users/invite",
            json={"email": _ADMIN, "label": "Doublon"},
            headers=admin,
        ).status_code == 409
        # Créer une invitation exige le rôle superadmin.
        assert client.post(
            "/api/admin/users/invite",
            json={"email": "x@example.com", "label": "X"},
        ).status_code == 401

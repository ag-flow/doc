"""Préférences d'interface par utilisateur (key/value JSONB, /api/me/preferences)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from docflow.app import app

_JWT_SECRET = "test_jwt_user_prefs"
_EMAIL = "prefs@example.com"
_PW = "prefs_pw_123456"


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    client.post(
        "/api/setup/init-admin",
        json={"username": "prefs", "email": _EMAIL, "password": _PW},
    )
    login = client.post("/api/auth/login", json={"email": _EMAIL, "password": _PW})
    assert login.status_code == 200, login.text
    token = client.cookies.get("docflow_session")
    client.cookies.clear()
    return {"docflow_session": token}


def test_preferences_roundtrip(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        key = "doc-columns:ws:bloc"

        # Jamais enregistrée → value null.
        r = client.get(f"/api/me/preferences/{key}", cookies=hdrs)
        assert r.status_code == 200
        assert r.json() == {"key": key, "value": None}

        # Upsert + relecture.
        cols = {"prop_statut": False, "type": True}
        assert client.put(
            f"/api/me/preferences/{key}", json={"value": cols}, cookies=hdrs
        ).status_code == 200
        assert client.get(f"/api/me/preferences/{key}", cookies=hdrs).json()["value"] == cols

        # Remplacement (upsert, pas d'append).
        client.put(f"/api/me/preferences/{key}", json={"value": {"a": 1}}, cookies=hdrs)
        assert client.get(f"/api/me/preferences/{key}", cookies=hdrs).json()["value"] == {"a": 1}

        # value null = effacer (retour au défaut).
        client.put(f"/api/me/preferences/{key}", json={"value": None}, cookies=hdrs)
        assert client.get(f"/api/me/preferences/{key}", cookies=hdrs).json()["value"] is None


def test_preferences_rejects_bad_input(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        # Clé hors format (majuscules / caractères interdits).
        assert client.get("/api/me/preferences/Bad%20Key", cookies=hdrs).status_code == 422
        # Valeur trop volumineuse.
        big = {"x": "y" * 20_000}
        r = client.put("/api/me/preferences/big", json={"value": big}, cookies=hdrs)
        assert r.status_code == 422
        # Fail closed : sans token.
        assert client.get("/api/me/preferences/doc-columns:a:b").status_code == 401

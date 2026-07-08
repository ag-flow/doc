from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from docflow.app import app

_JWT_SECRET = "test_jwt_secret_events_discovery"
_EMAIL = "disco@example.com"
_PW = "disco_pw_12345"


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    client.post(
        "/api/setup/init-admin",
        json={"username": "disco", "email": _EMAIL, "password": _PW},
    )
    login = client.post("/api/auth/login", json={"email": _EMAIL, "password": _PW})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_schemas_requires_auth() -> None:
    # Sans lifespan : le 401 tombe avant tout accès DB (token manquant).
    client = TestClient(app)
    assert client.get("/api/schemas").status_code == 401


def test_schema_catalog_and_versions(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)

        r = client.get("/api/schemas", headers=hdrs)
        assert r.status_code == 200
        body = r.json()
        assert body["specVersion"]
        assert body["revision"].startswith("sha256:")
        codes = {e["eventCode"] for e in body["events"]}
        assert len(codes) == 6
        assert "docflow.document.created.v1" in codes

        r = client.get("/api/schemas/docflow.document.created.v1/versions", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["versions"] == [1]

        r = client.get("/api/schemas/docflow.document.created.v1/versions/1", headers=hdrs)
        assert r.status_code == 200
        schema = r.json()
        assert schema["dataSchema"]["required"] == [
            "documentId",
            "workspaceSlug",
            "blockSlug",
            "title",
        ]
        assert schema["hash"].startswith("sha256:")

        # Inconnus → 404 explicite.
        assert (
            client.get("/api/schemas/docflow.nope.v1/versions", headers=hdrs).status_code == 404
        )
        assert (
            client.get(
                "/api/schemas/docflow.document.created.v1/versions/2", headers=hdrs
            ).status_code
            == 404
        )

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import docflow.app
from docflow.app import app

_BASE_ENV = {
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_PASSWORD": "s3cr3t",
    "JWT_SECRET": "jwt_key",
}


def test_health_returns_200_with_db_up(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
) -> None:
    """GET /health returns 200 and status=ok when the DB is reachable."""
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)

    with TestClient(app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] is True


def test_health_returns_503_when_db_query_fails(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
) -> None:
    """GET /health returns 503 when the DB becomes unreachable after startup."""
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)

    with TestClient(app) as client:
        monkeypatch.setattr(
            docflow.app,
            "_check_db",
            AsyncMock(side_effect=OSError("connection lost")),
        )
        resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.json()["status"] == "error"

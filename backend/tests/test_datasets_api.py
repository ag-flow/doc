"""Tests du router REST datasets (round-trip HTTP via TestClient).

Le front de la Feature 5 consomme ce REST : on couvre le cycle complet
(dataset → colonnes → lignes → détail → query → patch/delete → export/import CSV)
plus les rejets (auth, isolation workspace, slug dupliqué, type invalide).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from docflow.app import app

_JWT_SECRET = "test_jwt_secret_datasets"
_EMAIL = "bootstrap@example.com"
_PW = "bootstrap_pw_123"
_WS = "test-ws"


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    return TestClient(app)


def _auth_headers(client: TestClient) -> dict[str, str]:
    setup = client.post(
        "/api/setup/init-admin",
        json={"username": "bootstrap", "email": _EMAIL, "password": _PW},
    )
    assert setup.status_code == 201, setup.text
    login = client.post("/api/auth/login", json={"email": _EMAIL, "password": _PW})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_datasets_require_auth(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        resp = client.get(f"/api/workspaces/{_WS}/datasets")
    assert resp.status_code == 401


async def test_datasets_full_cycle(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
    test_workspace: dict,
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth_headers(client)
        base = f"/api/workspaces/{_WS}/datasets"

        # Création dataset
        r = client.post(base, json={"slug": "tasks", "label": "Tasks"}, headers=hdrs)
        assert r.status_code == 201, r.text
        ds_id = r.json()["id"]

        # Liste
        r = client.get(base, headers=hdrs)
        assert r.status_code == 200
        assert any(d["slug"] == "tasks" for d in r.json())

        # Colonnes
        assert (
            client.post(
                f"{base}/{ds_id}/columns",
                json={"slug": "name", "label": "Name", "type": "text"},
                headers=hdrs,
            ).status_code
            == 201
        )
        r = client.post(
            f"{base}/{ds_id}/columns",
            json={"slug": "qty", "label": "Qty", "type": "int"},
            headers=hdrs,
        )
        assert r.status_code == 201
        assert r.json()["type"] == "int"

        # Lignes
        r = client.post(
            f"{base}/{ds_id}/rows",
            json={"cells": {"name": "alpha", "qty": "5"}},
            headers=hdrs,
        )
        assert r.status_code == 201
        row_low = r.json()["row_id"]
        r = client.post(
            f"{base}/{ds_id}/rows",
            json={"cells": {"name": "beta", "qty": "20"}},
            headers=hdrs,
        )
        assert r.status_code == 201

        # Détail
        r = client.get(f"{base}/{ds_id}", headers=hdrs)
        assert r.status_code == 200
        detail = r.json()
        assert [c["slug"] for c in detail["columns"]] == ["name", "qty"]
        assert len(detail["rows"]) == 2

        # Query (filtre qty >= 10 → une seule ligne)
        r = client.post(
            f"{base}/{ds_id}/query",
            json={"filters": [{"column": "qty", "op": "gte", "value": "10"}]},
            headers=hdrs,
        )
        assert r.status_code == 200
        result = r.json()
        assert result["total"] == 1
        assert result["rows"][0]["cells"]["name"] == "beta"

        # PATCH colonne (label)
        r = client.patch(
            f"{base}/{ds_id}/columns/qty",
            json={"label": "Quantity"},
            headers=hdrs,
        )
        assert r.status_code == 200
        assert r.json()["label"] == "Quantity"

        # PATCH ligne (met à jour une cellule)
        r = client.patch(
            f"{base}/{ds_id}/rows/{row_low}",
            json={"cells": {"qty": "7"}},
            headers=hdrs,
        )
        assert r.status_code == 200
        assert r.json()["updated"] is True

        # DELETE ligne
        r = client.delete(f"{base}/{ds_id}/rows/{row_low}", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["deleted"] is True

        # Export CSV
        r = client.get(f"{base}/{ds_id}/export-csv", headers=hdrs)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]
        lines = r.text.strip().splitlines()
        assert lines[0] == "name,qty"
        assert "beta,20" in r.text

        # DELETE colonne
        r = client.delete(f"{base}/{ds_id}/columns/name", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["column_slug"] == "name"

        # Import CSV → crée un nouveau dataset
        r = client.post(
            f"{base}/import-csv",
            json={
                "slug": "imported",
                "label": "Imported",
                "csv": "city,pop\nParis,100\nLyon,50\n",
                "has_header": True,
            },
            headers=hdrs,
        )
        assert r.status_code == 200, r.text
        imported = r.json()
        assert imported["columns_created"] == 2
        assert imported["rows_created"] == 2
        assert imported["dataset_id"]


async def test_dataset_out_of_workspace_404(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
    test_workspace: dict,
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth_headers(client)
        base = f"/api/workspaces/{_WS}/datasets"

        r = client.post(base, json={"slug": "mine", "label": "Mine"}, headers=hdrs)
        ds_id = r.json()["id"]

        # Second workspace : le dataset du premier n'y est pas visible → 404
        assert (
            client.post(
                "/api/workspaces",
                json={"slug": "other-ws", "label": "Other"},
                headers=hdrs,
            ).status_code
            == 201
        )
        r = client.get(f"/api/workspaces/other-ws/datasets/{ds_id}", headers=hdrs)
        assert r.status_code == 404


async def test_dataset_duplicate_slug_409(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
    test_workspace: dict,
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth_headers(client)
        base = f"/api/workspaces/{_WS}/datasets"
        assert (
            client.post(base, json={"slug": "dup", "label": "Dup"}, headers=hdrs).status_code == 201
        )
        r = client.post(base, json={"slug": "dup", "label": "Dup2"}, headers=hdrs)
        assert r.status_code == 409


async def test_invalid_column_type_422(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
    test_workspace: dict,
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth_headers(client)
        base = f"/api/workspaces/{_WS}/datasets"
        ds_id = client.post(base, json={"slug": "typed", "label": "Typed"}, headers=hdrs).json()[
            "id"
        ]
        r = client.post(
            f"{base}/{ds_id}/columns",
            json={"slug": "bad", "label": "Bad", "type": "nope"},
            headers=hdrs,
        )
        assert r.status_code == 422

"""Contrat OpenAPI consommable (épic Interopérabilité).

Le schéma doit déclarer un `servers[0].url` ABSOLU (sinon l'importeur de contrat
devpod construit des URLs relatives rejetées par son anti-SSRF), rester servi
sans authentification, et exposer HTTPBearer dans securitySchemes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from docflow.app import app


def test_openapi_public_avec_servers_absolu_et_bearer(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://doc.example")
    with TestClient(app) as client:
        r = client.get("/openapi.json")  # aucun en-tête d'auth
    assert r.status_code == 200  # servi sans authentification
    spec = r.json()
    assert spec["servers"][0]["url"] == "https://doc.example"
    assert "HTTPBearer" in spec["components"]["securitySchemes"]
    # Le catch-all SPA n'intercepte pas : on a bien un schéma OpenAPI, pas du HTML.
    assert spec["openapi"].startswith("3.")


def test_openapi_servers_derive_des_entetes_proxy(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str
) -> None:
    """Sans public_base_url, l'URL de base est dérivée de X-Forwarded-* (proxy)."""
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    with TestClient(app) as client:
        r = client.get(
            "/openapi.json",
            headers={"x-forwarded-proto": "https", "x-forwarded-host": "proxy.example"},
        )
    assert r.status_code == 200
    assert r.json()["servers"][0]["url"] == "https://proxy.example"

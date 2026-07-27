"""Base URL dérivée du portail (repli quand public_base_url n'est pas configurée)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from docflow.app import app
from docflow.config import base_url


class _Configured:
    public_base_url = "https://cfg.example"


class _Empty:
    public_base_url = None


def test_effective_prefers_configured() -> None:
    base_url.set_derived_base_url("https://derived.example")
    assert base_url.effective_base_url(_Configured()) == "https://cfg.example"


def test_effective_falls_back_to_derived() -> None:
    base_url.set_derived_base_url("https://derived.example")
    assert base_url.effective_base_url(_Empty()) == "https://derived.example"


def test_set_ignores_empty_values() -> None:
    base_url.set_derived_base_url("https://kept.example")
    base_url.set_derived_base_url("")
    base_url.set_derived_base_url(None)
    assert base_url.get_derived_base_url() == "https://kept.example"


def test_middleware_captures_base_url_from_request(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str
) -> None:
    base_url.set_derived_base_url(None)  # reset (ignore ne remet pas à None…)
    base_url._derived_base_url = None  # reset dur pour le test
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", "test_jwt_base_url")
    # Pas de PUBLIC_BASE_URL → le middleware doit dériver depuis la requête.
    with TestClient(app) as client:
        # X-Forwarded-* prioritaires (cas derrière proxy / Cloudflare).
        r = client.get(
            "/api/schemas",
            headers={"x-forwarded-proto": "https", "x-forwarded-host": "doc.yoops.org"},
        )
        assert r.status_code == 200
    assert base_url.get_derived_base_url() == "https://doc.yoops.org"

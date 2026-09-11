"""ATDD — Surface REST des artefacts (fiche 46d3f95a).

Couvre les nouveautés bâties sur l'existant : override de nom/media_type à
l'upload, `?disposition=attachment` sur le GET de contenu, et l'endpoint
`/link` qui émet un lien signé de courte durée (équivalent REST du tool MCP).
"""

from __future__ import annotations

import asyncio
import re

import asyncpg
import pytest
from fastapi.testclient import TestClient

from docflow.app import app

_JWT_SECRET = "test_jwt_artifacts_rest"
_ADMIN = "art-admin@example.com"
_PW = "art_pw_123456"
_WS = "art-rest-ws"
_PNG = b"\x89PNG\r\n\x1a\n" + b"payload-rest"


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    return TestClient(app)


def _bootstrap(client: TestClient) -> dict[str, str]:
    client.post(
        "/api/setup/init-admin",
        json={"username": "artadmin", "email": _ADMIN, "password": _PW},
    )
    login = client.post("/api/auth/login", json={"email": _ADMIN, "password": _PW})
    assert login.status_code == 200, login.text
    admin = {}  # TestClient garde le cookie de session dans son jar
    r = client.post("/api/workspaces", json={"slug": _WS, "label": "Art WS"}, headers=admin)
    assert r.status_code == 201, r.text
    return admin


def _upload(
    client: TestClient, admin: dict[str, str], *, data: dict[str, str] | None = None
) -> dict[str, object]:
    r = client.post(
        f"/api/workspaces/{_WS}/artifacts",
        files={"file": ("logo.png", _PNG, "image/png")},
        data=data or {},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_upload_disposition_and_link_roundtrip(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        admin = _bootstrap(client)
        created = _upload(client, admin)
        aid = created["id"]

        base = f"/api/workspaces/{_WS}/artifacts/{aid}"

        # Contenu inline par défaut.
        inline = client.get(base, headers=admin)
        assert inline.status_code == 200
        assert inline.headers["content-disposition"].startswith("inline")
        assert inline.headers["x-content-type-options"] == "nosniff"

        # disposition=attachment force le téléchargement.
        att = client.get(base + "?disposition=attachment", headers=admin)
        assert att.status_code == 200
        assert att.headers["content-disposition"].startswith("attachment")

        # Valeur illégale rejetée par le pattern.
        assert client.get(base + "?disposition=bogus", headers=admin).status_code == 422

        # /link émet une URL signée, exploitable SANS Bearer.
        link = client.get(base + "/link", headers=admin)
        assert link.status_code == 200
        payload = link.json()
        assert payload["expires_in_seconds"] > 0
        m = re.match(rf".*{aid}/download\?exp=\d+&sig=[0-9a-f]{{64}}$", payload["url"])
        assert m is not None, payload["url"]

        signed = client.get(payload["url"])  # pas d'en-tête Authorization
        assert signed.status_code == 200
        assert signed.content == _PNG
        assert signed.headers["content-disposition"].startswith("attachment")


def test_upload_filename_and_media_type_override(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        admin = _bootstrap(client)
        created = _upload(client, admin, data={"filename": "capture.png"})
        assert created["filename"] == "capture.png"

        # media_type hors whitelist → 422 (jamais servir un type actif).
        r = client.post(
            f"/api/workspaces/{_WS}/artifacts",
            files={"file": ("x.png", _PNG + b"2", "image/png")},
            data={"media_type": "text/html"},
            headers=admin,
        )
        assert r.status_code == 422, r.text


def test_link_unknown_artifact_404(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    import uuid

    with _client(monkeypatch, test_schema_url) as client:
        admin = _bootstrap(client)
        r = client.get(f"/api/workspaces/{_WS}/artifacts/{uuid.uuid4()}/link", headers=admin)
        assert r.status_code == 404


def test_list_artifacts_rest_and_filters(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        admin = _bootstrap(client)
        a = _upload(client, admin)  # logo.png (_PNG)
        # Un second artefact, nom distinct.
        r = client.post(
            f"/api/workspaces/{_WS}/artifacts",
            files={"file": ("rapport.png", _PNG + b"x", "image/png")},
            headers=admin,
        )
        assert r.status_code == 201, r.text

        base = f"/api/workspaces/{_WS}/artifacts"
        # Liste complète : colonnes de table + refcount, pagination.
        full = client.get(base, headers=admin).json()
        assert full["total"] == 2 and len(full["items"]) == 2
        assert {"sha256", "crc32", "created_by", "refcount"} <= set(full["items"][0])

        # Filtre nom partiel.
        by_name = client.get(base + "?filename=rapp", headers=admin).json()
        assert by_name["total"] == 1 and by_name["items"][0]["filename"] == "rapport.png"

        # Filtre sha256 exact.
        by_sha = client.get(base + f"?sha256={a['sha256']}", headers=admin).json()
        assert by_sha["total"] == 1 and by_sha["items"][0]["id"] == a["id"]

        # sha256 mal formé → 422 (validation du pattern).
        assert client.get(base + "?sha256=xyz", headers=admin).status_code == 422


@pytest.fixture(autouse=True)
def _cleanup_ws(test_schema_url: str) -> object:
    yield None

    async def _drop() -> None:
        conn = await asyncpg.connect(test_schema_url)
        try:
            await conn.execute("DELETE FROM workspace WHERE slug = $1", _WS)
        finally:
            await conn.close()

    asyncio.run(_drop())

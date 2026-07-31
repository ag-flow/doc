"""F1 — Registre des types d'artefact (whitelist administrable).

Couvre le seed, le denylist de sécurité (types actifs interdits), le CRUD
service, et le RBAC des endpoints (lecture authentifiée, écriture admin).
"""

from __future__ import annotations

import asyncio

import asyncpg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from docflow.app import app
from docflow.artifacts import media_types

_JWT_SECRET = "test_jwt_artifact_types"
_ADMIN = "at-admin@example.com"
_USER = "at-user@example.com"
_PW = "at_pw_12345678"


# ── Service : seed + denylist + CRUD ─────────────────────────────────────────


async def test_seed_present(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        allowed = await media_types.load_allowed_map(conn)
    # Quelques entrées du seed (migration 0064).
    assert allowed["pdf"] == "application/pdf"
    assert allowed["png"] == "image/png"
    assert allowed["zip"] == "application/zip"


async def test_add_and_list_type(db_pool: asyncpg.Pool) -> None:
    try:
        created = await media_types.add_type(
            db_pool, extension="TAR", media_type="application/x-tar", label="Archive TAR"
        )
        assert created["extension"] == "tar"  # normalisé en minuscule
        assert created["media_type"] == "application/x-tar"
        rows = await media_types.list_types(db_pool)
        assert any(r["extension"] == "tar" for r in rows)
    finally:
        await db_pool.execute("DELETE FROM artifact_media_type WHERE extension = 'tar'")


async def test_add_duplicate_extension_409(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await media_types.add_type(
            db_pool, extension="pdf", media_type="application/pdf", label="x"
        )
    assert exc.value.status_code == 409


@pytest.mark.parametrize(
    "bad",
    ["text/html", "application/xhtml+xml", "application/javascript", "text/javascript"],
)
async def test_denylist_rejected_on_add(db_pool: asyncpg.Pool, bad: str) -> None:
    """Un type actif (XSS servi depuis notre origine) ne peut jamais être ajouté."""
    with pytest.raises(HTTPException) as exc:
        await media_types.add_type(db_pool, extension="hax", media_type=bad, label="x")
    assert exc.value.status_code == 422
    gone = await db_pool.fetchval(
        "SELECT 1 FROM artifact_media_type WHERE extension = 'hax'"
    )
    assert gone is None


async def test_denylist_rejected_on_update(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await media_types.update_type(db_pool, "txt", media_type="text/html", label="x")
    assert exc.value.status_code == 422
    # txt inchangé
    async with db_pool.acquire() as conn:
        allowed = await media_types.load_allowed_map(conn)
    assert allowed["txt"] == "text/plain"


async def test_update_and_delete_roundtrip(db_pool: asyncpg.Pool) -> None:
    await media_types.add_type(
        db_pool, extension="rtf", media_type="application/rtf", label="RTF"
    )
    try:
        updated = await media_types.update_type(
            db_pool, "rtf", media_type="text/rtf", label="Texte enrichi"
        )
        assert updated["media_type"] == "text/rtf"
        assert updated["label"] == "Texte enrichi"
    finally:
        await media_types.delete_type(db_pool, "rtf")
    gone = await db_pool.fetchval("SELECT 1 FROM artifact_media_type WHERE extension = 'rtf'")
    assert gone is None


async def test_update_unknown_404(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await media_types.update_type(db_pool, "zzz", media_type="application/zip", label="")
    assert exc.value.status_code == 404


# ── Endpoints : RBAC ─────────────────────────────────────────────────────────


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    return TestClient(app)


def _setup(client: TestClient, test_schema_url: str) -> tuple[dict[str, str], dict[str, str]]:
    client.post(
        "/api/setup/init-admin",
        json={"username": "atadmin", "email": _ADMIN, "password": _PW},
    )
    admin = {
        "Authorization": "Bearer "
        + client.post(
            "/api/auth/login", json={"email": _ADMIN, "password": _PW}
        ).json()["access_token"]
    }
    client.post(
        "/api/admin/users",
        json={"email": _USER, "label": "AT User", "password": _PW},
        headers=admin,
    )

    async def _validate() -> None:
        conn = await asyncpg.connect(test_schema_url)
        try:
            await conn.execute(
                "UPDATE app_user SET validated = true, disabled = false WHERE email = $1", _USER
            )
        finally:
            await conn.close()

    asyncio.run(_validate())
    user = {
        "Authorization": "Bearer "
        + client.post(
            "/api/auth/login", json={"email": _USER, "password": _PW}
        ).json()["access_token"]
    }
    return admin, user


def test_read_authenticated_write_admin_only(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        admin, user = _setup(client, test_schema_url)

        # Lecture : utilisateur validé OK.
        r = client.get("/api/artifact-types", headers=user)
        assert r.status_code == 200
        assert any(t["extension"] == "pdf" for t in r.json())

        # Écriture : utilisateur non-admin refusé.
        assert (
            client.post(
                "/api/admin/artifact-types",
                json={"extension": "heic", "media_type": "image/heic", "label": "HEIC"},
                headers=user,
            ).status_code
            == 403
        )

        # Écriture admin OK, puis suppression.
        created = client.post(
            "/api/admin/artifact-types",
            json={"extension": "heic", "media_type": "image/heic", "label": "HEIC"},
            headers=admin,
        )
        assert created.status_code == 201, created.text
        assert client.delete("/api/admin/artifact-types/heic", headers=admin).status_code == 204

        # Denylist via l'API.
        assert (
            client.post(
                "/api/admin/artifact-types",
                json={"extension": "htm", "media_type": "text/html", "label": "x"},
                headers=admin,
            ).status_code
            == 422
        )

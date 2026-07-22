"""Tests des secrets HMAC (store par-utilisateur, valeur copiable).

Couvre le cycle HTTP (générer / lister sans valeur / révéler / supprimer),
l'isolation vis-à-vis des secrets génériques, la résolution `${hmac://<uuid>}`
par le résolveur (voie du worker d'émission), et le validateur secret_ref.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from docflow.app import app
from docflow.schemas.events_producer import EventsProducerConfigUpdate
from docflow.secrets.resolver import resolve
from docflow.secrets.secret import Secret

_JWT_SECRET = "test_jwt_secret_hmac"
_EMAIL = "hmac@example.com"
_PW = "hmac_pw_123456"
_ENC_KEY = Fernet.generate_key().decode()


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    monkeypatch.setenv("ENCRYPTION_KEY", _ENC_KEY)
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    client.post(
        "/api/setup/init-admin",
        json={"username": "hmac", "email": _EMAIL, "password": _PW},
    )
    login = client.post("/api/auth/login", json={"email": _EMAIL, "password": _PW})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_hmac_requires_auth(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        assert client.get("/api/hmac-secrets").status_code == 401


def test_hmac_generate_list_reveal(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        # Génération (pas de value fournie) → une valeur est renvoyée UNE fois.
        r = client.post(
            "/api/hmac-secrets", json={"label": "WF prod", "slug": "wf-prod"}, headers=hdrs
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["value"], "la valeur générée doit être renvoyée"
        sid, gen_value = body["id"], body["value"]

        # Liste : jamais de valeur exposée.
        r = client.get("/api/hmac-secrets", headers=hdrs)
        assert r.status_code == 200
        items = r.json()
        assert any(i["slug"] == "wf-prod" for i in items)
        assert all("value" not in i for i in items)

        # Reveal : re-révèle exactement la même valeur (bouton copier).
        r = client.get(f"/api/hmac-secrets/{sid}/reveal", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["value"] == gen_value


def test_hmac_provided_value_isolated_from_generic(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        r = client.post(
            "/api/hmac-secrets",
            json={"label": "Shared", "slug": "shared", "value": "my-shared-secret"},
            headers=hdrs,
        )
        assert r.status_code == 201, r.text
        sid = r.json()["id"]

        # Un secret HMAC n'apparaît PAS dans les secrets génériques (invariant préservé).
        r = client.get("/api/admin/secrets", headers=hdrs)
        assert r.status_code == 200
        assert all(s["slug"] != "shared" for s in r.json())

        # La valeur fournie est bien celle stockée.
        r = client.get(f"/api/hmac-secrets/{sid}/reveal", headers=hdrs)
        assert r.json()["value"] == "my-shared-secret"


def test_hmac_reveal_unknown_404(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        r = client.get(f"/api/hmac-secrets/{uuid.uuid4()}/reveal", headers=hdrs)
        assert r.status_code == 404


def test_hmac_delete(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        sid = client.post(
            "/api/hmac-secrets", json={"label": "X", "slug": "x"}, headers=hdrs
        ).json()["id"]
        assert client.delete(f"/api/hmac-secrets/{sid}", headers=hdrs).status_code == 204
        assert client.get(f"/api/hmac-secrets/{sid}/reveal", headers=hdrs).status_code == 404


async def test_resolver_hmac_ref(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    """`${hmac://<uuid>}` doit se résoudre en la valeur déchiffrée (voie worker)."""
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        sid = client.post(
            "/api/hmac-secrets",
            json={"label": "WF", "slug": "wf", "value": "resolved-secret-9"},
            headers=hdrs,
        ).json()["id"]

    pool = await asyncpg.create_pool(test_schema_url)
    try:
        value = await resolve(
            Secret(f"${{hmac://{sid}}}"), harpocrate_url=None, pool=pool, enc_key=_ENC_KEY
        )
    finally:
        await pool.close()
    assert value == "resolved-secret-9"


async def test_resolver_hmac_ref_unknown_raises() -> None:
    pool = None
    with pytest.raises(ValueError, match="pool and enc_key"):
        await resolve(Secret(f"${{hmac://{uuid.uuid4()}}}"), harpocrate_url=None, pool=pool)


def test_events_secret_ref_accepts_hmac() -> None:
    m = EventsProducerConfigUpdate(secret_ref=f"${{hmac://{uuid.uuid4()}}}")
    assert m.secret_ref is not None and m.secret_ref.startswith("${hmac://")


def test_events_secret_ref_rejects_plain() -> None:
    with pytest.raises(ValueError, match="vault://|hmac://"):
        EventsProducerConfigUpdate(secret_ref="plain-not-a-ref")

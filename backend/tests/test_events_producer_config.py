from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from docflow.app import app
from docflow.events import catalog, outbox, producer_config, producer_router

_JWT_SECRET = "test_jwt_secret_events_producer"
_EMAIL = "prod@example.com"
_PW = "prod_pw_123456"
_VAULT_REF = "${vault://harpocrate:/docflow/hmac}"
_CREATED = "docflow.document.created.v1"


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
async def clean_config(db_pool: asyncpg.Pool) -> AsyncIterator[None]:
    """Isole la ligne singleton et remet l'outbox à l'état neutre après le test."""
    await db_pool.execute("DELETE FROM events_producer_config")
    await db_pool.execute("DELETE FROM event_outbox")
    yield
    await db_pool.execute("DELETE FROM events_producer_config")
    await db_pool.execute("DELETE FROM event_outbox")
    outbox.configure(enabled=False, source="docflow", allowed_events=None)


class _EnvSettings:
    workflow_ingestion_url = "https://wf.example"
    workflow_source_id = "docflow"
    workflow_hmac_secret = "sekret"
    event_source = "docflow-prod"


# ── Service : get / update ───────────────────────────────────────────────────


async def test_get_returns_defaults(db_pool: asyncpg.Pool, clean_config: None) -> None:
    cfg = await producer_config.get_config(db_pool)
    assert cfg["enabled"] is False
    assert cfg["ingestion_url"] is None
    assert cfg["source_id"] is None
    assert cfg["source_uri"] == "docflow"
    assert list(cfg["allowed_events"]) == []
    assert cfg["secret_ref"] is None


async def test_update_changes_fields_and_masks_secret(
    db_pool: asyncpg.Pool, clean_config: None
) -> None:
    cfg = await producer_config.update_config(
        db_pool,
        {
            "enabled": True,
            "ingestion_url": "https://wf",
            "source_id": "docflow",
            "source_uri": "docflow-prod",
            "allowed_events": [_CREATED],
            "secret_ref": _VAULT_REF,
        },
    )
    assert cfg["enabled"] is True
    assert cfg["source_uri"] == "docflow-prod"
    assert list(cfg["allowed_events"]) == [_CREATED]
    # Le secret est stocké mais JAMAIS exposé dans la sortie API.
    out = producer_router._to_out(cfg).model_dump()
    assert out["secret_configured"] is True
    assert "secret_ref" not in out
    assert "vault://" not in json.dumps(out)


async def test_update_is_partial(db_pool: asyncpg.Pool, clean_config: None) -> None:
    await producer_config.update_config(
        db_pool, {"ingestion_url": "https://wf", "secret_ref": _VAULT_REF}
    )
    cfg = await producer_config.update_config(db_pool, {"enabled": True})
    assert cfg["enabled"] is True
    assert cfg["ingestion_url"] == "https://wf"  # préservé
    assert cfg["secret_ref"] is not None  # préservé


# ── Outbox : allowlist fail-closed + rétro-compat ────────────────────────────


async def _enqueue(pool: asyncpg.Pool, code: str) -> None:
    async with pool.acquire() as conn, conn.transaction():
        await outbox.enqueue(conn, event_code=code, workspace_wk=None, business={"documentId": "d"})


async def test_allowlist_fail_closed(db_pool: asyncpg.Pool, clean_config: None) -> None:
    # Set explicite vide → aucun relais, même pour un eventCode connu.
    outbox.configure(enabled=True, source="x", allowed_events=set())
    await _enqueue(db_pool, _CREATED)
    assert await db_pool.fetchval("SELECT count(*) FROM event_outbox") == 0
    # Set contenant le code → une ligne écrite.
    outbox.configure(enabled=True, source="x", allowed_events={_CREATED})
    await _enqueue(db_pool, _CREATED)
    assert await db_pool.fetchval("SELECT count(*) FROM event_outbox") == 1


async def test_retro_compat_no_allowlist_emits(db_pool: asyncpg.Pool, clean_config: None) -> None:
    # configure sans allowed_events (None) = tous autorisés (rétro-compat).
    outbox.configure(enabled=True, source="x")
    await _enqueue(db_pool, _CREATED)
    assert await db_pool.fetchval("SELECT count(*) FROM event_outbox") == 1


async def test_reconcile_applies_db_config(db_pool: asyncpg.Pool, clean_config: None) -> None:
    await producer_config.update_config(
        db_pool,
        {"enabled": True, "source_uri": "src", "allowed_events": ["docflow.document.moved.v1"]},
    )
    await outbox.reconcile(db_pool)
    assert outbox.is_enabled() is True
    assert outbox._source == "src"
    assert outbox._allowed_events == {"docflow.document.moved.v1"}


# ── Seed depuis l'env ────────────────────────────────────────────────────────


async def test_seed_when_empty(db_pool: asyncpg.Pool, clean_config: None) -> None:
    await producer_config.seed_from_env_if_empty(db_pool, _EnvSettings())
    cfg = await producer_config.get_config(db_pool)
    assert cfg["enabled"] is True
    assert cfg["ingestion_url"] == "https://wf.example"
    assert cfg["source_id"] == "docflow"
    assert cfg["source_uri"] == "docflow-prod"
    assert set(cfg["allowed_events"]) == set(catalog.CATALOG.keys())
    # Le secret env n'est PAS recopié en clair : l'admin doit poser secret_ref.
    assert cfg["secret_ref"] is None


async def test_seed_migrates_vault_secret_ref(db_pool: asyncpg.Pool, clean_config: None) -> None:
    # Un secret env sous forme de RÉFÉRENCE vault (pointeur, pas le secret) est
    # migré → l'upgrade d'une instance déjà configurée ne coupe pas la livraison.
    class _VaultEnv:
        workflow_ingestion_url = "https://wf.example"
        workflow_source_id = "docflow"
        workflow_hmac_secret = "${vault://docflow:/workflow-hmac}"
        event_source = "docflow-prod"

    await producer_config.seed_from_env_if_empty(db_pool, _VaultEnv())
    cfg = await producer_config.get_config(db_pool)
    assert cfg["secret_ref"] == "${vault://docflow:/workflow-hmac}"


async def test_seed_does_not_overwrite(db_pool: asyncpg.Pool, clean_config: None) -> None:
    await producer_config.update_config(
        db_pool, {"enabled": True, "ingestion_url": "https://existing"}
    )
    await producer_config.seed_from_env_if_empty(db_pool, _EnvSettings())
    cfg = await producer_config.get_config(db_pool)
    assert cfg["ingestion_url"] == "https://existing"  # inchangé
    assert set(cfg["allowed_events"]) == set()  # pas seedé


async def test_seed_noop_when_env_absent(db_pool: asyncpg.Pool, clean_config: None) -> None:
    class _Empty:
        workflow_ingestion_url = None
        workflow_source_id = None
        workflow_hmac_secret = None
        event_source = "docflow"

    await producer_config.seed_from_env_if_empty(db_pool, _Empty())
    cfg = await producer_config.get_config(db_pool)
    assert cfg["enabled"] is False
    assert cfg["ingestion_url"] is None


# ── Router HTTP (superadmin) ─────────────────────────────────────────────────


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    client.post(
        "/api/setup/init-admin",
        json={"username": "prod", "email": _EMAIL, "password": _PW},
    )
    login = client.post("/api/auth/login", json={"email": _EMAIL, "password": _PW})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _reset(url: str) -> None:
    async def _do() -> None:
        conn = await asyncpg.connect(url)
        try:
            await conn.execute("DELETE FROM events_producer_config")
            await conn.execute("DELETE FROM event_outbox")
        finally:
            await conn.close()

    asyncio.run(_do())


def test_put_requires_superadmin() -> None:
    # Sans token : 401 avant tout accès DB.
    client = TestClient(app)
    assert client.put("/api/admin/events-producer", json={"enabled": True}).status_code == 401


def test_put_and_get_roundtrip(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    _reset(test_schema_url)
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        r = client.put(
            "/api/admin/events-producer",
            headers=hdrs,
            json={
                "enabled": True,
                "ingestion_url": "https://wf",
                "source_id": "docflow",
                "source_uri": "docflow-prod",
                "allowed_events": [_CREATED],
                "secret_ref": _VAULT_REF,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert body["allowed_events"] == [_CREATED]
        assert body["secret_configured"] is True
        # Le secret ne fuite jamais.
        assert "secret_ref" not in body
        assert "vault://" not in r.text

        g = client.get("/api/admin/events-producer", headers=hdrs)
        assert g.status_code == 200
        assert g.json()["source_uri"] == "docflow-prod"
        assert g.json()["secret_configured"] is True


def test_put_unknown_event_code_422(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    _reset(test_schema_url)
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        r = client.put(
            "/api/admin/events-producer",
            headers=hdrs,
            json={"allowed_events": ["docflow.does.not.exist.v1"]},
        )
        assert r.status_code == 422


def test_put_secret_ref_must_be_vault_422(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    _reset(test_schema_url)
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        r = client.put(
            "/api/admin/events-producer",
            headers=hdrs,
            json={"secret_ref": "plain-secret-in-clear"},
        )
        assert r.status_code == 422


def test_test_connection_ok(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    _reset(test_schema_url)
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        client.put(
            "/api/admin/events-producer",
            headers=hdrs,
            json={
                "enabled": True,
                "ingestion_url": "https://wf.example/events/ef7ae716",
                "secret_ref": _VAULT_REF,
            },
        )

        async def fake_resolve(secret_obj: Any, *, pool: Any, settings: Any) -> str:
            return "s3cr3t"

        calls: list[tuple[str, bytes, dict[str, str]]] = []

        async def fake_poster(url: str, body: bytes, headers: dict[str, str]) -> int:
            calls.append((url, body, headers))
            return 202

        monkeypatch.setattr(producer_router, "_resolve_secret", fake_resolve)
        monkeypatch.setattr(producer_router, "_poster", fake_poster)

        r = client.post("/api/admin/events-producer/test-connection", headers=hdrs)
        assert r.status_code == 200
        assert r.json() == {"status": 202, "ok": True}
        # Le POST vise l'URL d'envoi COMPLÈTE telle quelle (aucun ajout).
        assert calls[0][0] == "https://wf.example/events/ef7ae716"
        # L'event de test est hors catalogue et signé.
        env = json.loads(calls[0][1])
        assert env["_eventCode"] == "docflow.testevent.v1"
        assert "x-signature" in calls[0][2]

    # Aucune ligne outbox créée par le test-connection.
    async def _count() -> int:
        conn = await asyncpg.connect(test_schema_url)
        try:
            return await conn.fetchval("SELECT count(*) FROM event_outbox")  # type: ignore[no-any-return]
        finally:
            await conn.close()

    assert asyncio.run(_count()) == 0


def test_test_connection_incomplete_config_400(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    _reset(test_schema_url)
    with _client(monkeypatch, test_schema_url) as client:
        hdrs = _auth(client)
        r = client.post("/api/admin/events-producer/test-connection", headers=hdrs)
        assert r.status_code == 400

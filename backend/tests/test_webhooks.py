from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
from cryptography.fernet import Fernet

from docflow.schemas.webhook import WebhookCreate, WebhookUpdate
from docflow.webhooks import service as svc


def _key() -> str:
    return Fernet.generate_key().decode()


# ── Fixtures DB ───────────────────────────────────────────────────────────────

@pytest.fixture()
async def ws(db_pool: asyncpg.Pool) -> dict[str, Any]:
    row = await db_pool.fetchrow(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) "
        "RETURNING workspace_technical_key, slug",
        "hook-ws", "Hook Workspace",
    )
    assert row is not None
    yield dict(row)
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "hook-ws")


# ── Tests CRUD ────────────────────────────────────────────────────────────────

async def test_create_and_list_webhook(db_pool: asyncpg.Pool, ws: dict[str, Any]) -> None:
    key = _key()
    wh = await svc.create_webhook(
        db_pool,
        "hook-ws",
        WebhookCreate(
            label="Mon hook",
            url="https://example.com/{id_document}",
            headers={"X-Token": "secret"},
            events=["document.created"],
        ),
        encryption_key=key,
    )
    assert wh.label == "Mon hook"
    assert wh.headers == {"X-Token": "secret"}
    assert "document.created" in wh.events

    listing = await svc.list_webhooks(db_pool, "hook-ws", encryption_key=key)
    assert any(w.id == wh.id for w in listing)


async def test_headers_encrypted_at_rest(db_pool: asyncpg.Pool, ws: dict[str, Any]) -> None:
    """DoD 29.4 — headers_encrypted != JSON saisi."""
    key = _key()
    await svc.create_webhook(
        db_pool,
        "hook-ws",
        WebhookCreate(
            label="Enc test",
            url="https://example.com/",
            headers={"Authorization": "Bearer topsecret"},
            events=[],
        ),
        encryption_key=key,
    )
    row = await db_pool.fetchrow(
        "SELECT headers_encrypted FROM webhook_subscription WHERE workspace_technical_key = "
        "(SELECT workspace_technical_key FROM workspace WHERE slug = $1)",
        "hook-ws",
    )
    assert row is not None
    raw: bytes | None = row["headers_encrypted"]
    assert raw is not None
    assert b"topsecret" not in raw  # pas en clair
    import json as _json
    with pytest.raises(Exception):
        _json.loads(raw)  # ce n'est pas du JSON valide (c'est chiffré)


async def test_update_webhook(db_pool: asyncpg.Pool, ws: dict[str, Any]) -> None:
    key = _key()
    wh = await svc.create_webhook(
        db_pool, "hook-ws",
        WebhookCreate(label="Before", url="https://a.com/", events=["document.created"]),
        encryption_key=key,
    )
    updated = await svc.update_webhook(
        db_pool, "hook-ws", wh.id,
        WebhookUpdate(label="After", active=False),
        encryption_key=key,
    )
    assert updated.label == "After"
    assert updated.active is False


async def test_delete_webhook(db_pool: asyncpg.Pool, ws: dict[str, Any]) -> None:
    key = _key()
    wh = await svc.create_webhook(
        db_pool, "hook-ws",
        WebhookCreate(label="Del", url="https://b.com/", events=[]),
        encryption_key=key,
    )
    await svc.delete_webhook(db_pool, "hook-ws", wh.id)
    listing = await svc.list_webhooks(db_pool, "hook-ws", encryption_key=key)
    assert not any(w.id == wh.id for w in listing)


async def test_create_webhook_without_headers_no_key(
    db_pool: asyncpg.Pool, ws: dict[str, Any]
) -> None:
    """Pas de clé, pas de headers → OK."""
    wh = await svc.create_webhook(
        db_pool, "hook-ws",
        WebhookCreate(label="NoKey", url="https://c.com/", events=[]),
        encryption_key=None,
    )
    assert wh.headers == {}


async def test_create_webhook_with_headers_requires_key(
    db_pool: asyncpg.Pool, ws: dict[str, Any]
) -> None:
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.create_webhook(
            db_pool, "hook-ws",
            WebhookCreate(label="Bad", url="https://d.com/", headers={"H": "v"}, events=[]),
            encryption_key=None,
        )
    assert exc.value.status_code == 422


# ── Test fire-and-forget ──────────────────────────────────────────────────────

async def test_emit_event_fires_post(db_pool: asyncpg.Pool, ws: dict[str, Any]) -> None:
    """DoD 29.2 — abonnement created+updated → POST reçu avec substitution {id_document}."""
    key = _key()
    received: list[dict[str, Any]] = []

    # Abonnement actif
    wh = await svc.create_webhook(
        db_pool, "hook-ws",
        WebhookCreate(
            label="Fire",
            url="https://example.com/{id_document}",
            events=["document.created"],
        ),
        encryption_key=key,
    )

    doc_id = str(uuid.uuid4())
    snap = {"id": doc_id, "title": "T", "type": "page", "version": 1}

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    async def fake_post(url: str, **kwargs: Any) -> MagicMock:
        received.append({"url": url, "json": kwargs.get("json")})
        return mock_resp

    with patch("httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        instance.post = AsyncMock(side_effect=fake_post)
        MockClient.return_value = instance

        await svc.emit_event(db_pool, "hook-ws", "document.created", snap, encryption_key=key)

    assert len(received) == 1
    assert doc_id in received[0]["url"]
    assert received[0]["json"]["event"] == "document.created"
    assert received[0]["json"]["document"]["id"] == doc_id

    _ = wh  # used above


async def test_emit_event_external_down_does_not_raise(
    db_pool: asyncpg.Pool, ws: dict[str, Any]
) -> None:
    """DoD 29.3 — externe injoignable → pas d'exception propagée."""
    key = _key()
    await svc.create_webhook(
        db_pool, "hook-ws",
        WebhookCreate(label="Down", url="https://nowhere.invalid/", events=["document.created"]),
        encryption_key=key,
    )

    import httpx as httpx_mod
    with patch("httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        instance.post = AsyncMock(side_effect=httpx_mod.ConnectError("refused"))
        MockClient.return_value = instance

        # Ne doit pas lever d'exception
        await svc.emit_event(
            db_pool, "hook-ws", "document.created",
            {"id": str(uuid.uuid4()), "title": "T", "type": "page", "version": 1},
            encryption_key=key,
        )


async def test_test_webhook_returns_status_code(
    db_pool: asyncpg.Pool, ws: dict[str, Any]
) -> None:
    """DoD 29.6 — test webhook renvoie le code HTTP."""
    key = _key()
    wh = await svc.create_webhook(
        db_pool, "hook-ws",
        WebhookCreate(label="Test", url="https://example.com/", events=["document.created"]),
        encryption_key=key,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 204

    with patch("httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=None)
        instance.post = AsyncMock(return_value=mock_resp)
        MockClient.return_value = instance

        status, error = await svc.test_webhook(db_pool, "hook-ws", wh.id, encryption_key=key)

    assert status == 204
    assert error is None

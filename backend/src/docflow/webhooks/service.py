from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
import httpx
import structlog
from fastapi import HTTPException

from docflow.crypto import decrypt_headers, encrypt_headers
from docflow.db.helpers import require_workspace
from docflow.schemas.webhook import WebhookCreate, WebhookOut, WebhookUpdate

log = structlog.get_logger(__name__)

_WEBHOOK_TIMEOUT = 8.0


def _row_to_out(row: asyncpg.Record, headers: dict[str, str]) -> WebhookOut:
    return WebhookOut(
        id=row["id"],
        workspace_technical_key=row["workspace_technical_key"],
        label=row["label"],
        url=row["url"],
        headers=headers,
        events=list(row["events"]),
        active=row["active"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _decrypt_safe(key: str | None, data: bytes | None) -> dict[str, str]:
    if not data:
        return {}
    if not key:
        log.warning("webhook_headers_no_key")
        return {}
    try:
        return decrypt_headers(key, data)
    except Exception:
        log.warning("webhook_headers_decrypt_failed")
        return {}


async def list_webhooks(
    pool: asyncpg.Pool, ws_slug: str, *, encryption_key: str | None
) -> list[WebhookOut]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            "SELECT id, workspace_technical_key, label, url, headers_encrypted, "
            "       events, active, created_at, updated_at "
            "FROM webhook_subscription WHERE workspace_technical_key = $1 ORDER BY created_at",
            wk,
        )
    return [_row_to_out(r, _decrypt_safe(encryption_key, r["headers_encrypted"])) for r in rows]


async def get_webhook(
    pool: asyncpg.Pool, ws_slug: str, webhook_id: uuid.UUID, *, encryption_key: str | None
) -> WebhookOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            "SELECT id, workspace_technical_key, label, url, headers_encrypted, "
            "       events, active, created_at, updated_at "
            "FROM webhook_subscription WHERE id = $1 AND workspace_technical_key = $2",
            webhook_id,
            wk,
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} introuvable")
    return _row_to_out(row, _decrypt_safe(encryption_key, row["headers_encrypted"]))


async def create_webhook(
    pool: asyncpg.Pool, ws_slug: str, data: WebhookCreate, *, encryption_key: str | None
) -> WebhookOut:
    if data.headers and not encryption_key:
        raise HTTPException(
            status_code=422,
            detail="DOCFLOW_ENCRYPTION_KEY requis pour stocker des headers chiffrés",
        )
    enc = encrypt_headers(encryption_key, data.headers) if data.headers and encryption_key else None
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            "INSERT INTO webhook_subscription "
            "(workspace_technical_key, label, url, headers_encrypted, events, active) "
            "VALUES ($1, $2, $3, $4, $5, $6) "
            "RETURNING id, workspace_technical_key, label, url, headers_encrypted, "
            "          events, active, created_at, updated_at",
            wk,
            data.label,
            data.url,
            enc,
            data.events,
            data.active,
        )
    assert row is not None
    return _row_to_out(row, data.headers)


async def update_webhook(
    pool: asyncpg.Pool,
    ws_slug: str,
    webhook_id: uuid.UUID,
    data: WebhookUpdate,
    *,
    encryption_key: str | None,
) -> WebhookOut:
    raw = data.model_dump(exclude_unset=True)
    if not raw:
        return await get_webhook(pool, ws_slug, webhook_id, encryption_key=encryption_key)

    if "headers" in raw and raw["headers"] and not encryption_key:
        raise HTTPException(
            status_code=422,
            detail="DOCFLOW_ENCRYPTION_KEY requis pour stocker des headers chiffrés",
        )

    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        exists = await conn.fetchval(
            "SELECT id FROM webhook_subscription WHERE id = $1 AND workspace_technical_key = $2",
            webhook_id,
            wk,
        )
        if exists is None:
            raise HTTPException(status_code=404, detail=f"webhook {webhook_id} introuvable")

        sets: dict[str, object] = {}
        if "label" in raw:
            sets["label"] = raw["label"]
        if "url" in raw:
            sets["url"] = raw["url"]
        if "headers" in raw:
            h = raw["headers"] or {}
            sets["headers_encrypted"] = (
                encrypt_headers(encryption_key, h) if h and encryption_key else None
            )
        if "events" in raw:
            sets["events"] = raw["events"]
        if "active" in raw:
            sets["active"] = raw["active"]
        sets["updated_at"] = "now()"

        # Construction sécurisée de la clause SET (clés connues, pas d'interpolation user)
        parts = []
        values: list[object] = [webhook_id]
        for k, v in sets.items():
            if v == "now()":
                parts.append(f"{k} = now()")
            else:
                values.append(v)
                parts.append(f"{k} = ${len(values)}")

        row = await conn.fetchrow(
            "UPDATE webhook_subscription SET " + ", ".join(parts) + " WHERE id = $1 "
            "RETURNING id, workspace_technical_key, label, url, headers_encrypted, "
            "          events, active, created_at, updated_at",
            *values,
        )
    assert row is not None
    return _row_to_out(row, _decrypt_safe(encryption_key, row["headers_encrypted"]))


async def delete_webhook(pool: asyncpg.Pool, ws_slug: str, webhook_id: uuid.UUID) -> None:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        deleted = await conn.fetchval(
            "DELETE FROM webhook_subscription WHERE id = $1 AND workspace_technical_key = $2 "
            "RETURNING id",
            webhook_id,
            wk,
        )
    if deleted is None:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} introuvable")


async def test_webhook(
    pool: asyncpg.Pool,
    ws_slug: str,
    webhook_id: uuid.UUID,
    *,
    encryption_key: str | None,
) -> tuple[int | None, str | None]:
    """Envoie un payload synthétique et retourne (status_code, error)."""
    wh = await get_webhook(pool, ws_slug, webhook_id, encryption_key=encryption_key)
    payload = {
        "event": "document.created",
        "occurred_at": datetime.now(UTC).isoformat(),
        "workspace": ws_slug,
        "document": {
            "id": "00000000-0000-0000-0000-000000000000",
            "title": "Test webhook",
            "type": "page",
            "version": 1,
        },
    }
    url = wh.url.replace("{id_document}", "00000000-0000-0000-0000-000000000000")
    try:
        async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=wh.headers)
        return resp.status_code, None
    except Exception as exc:
        return None, str(exc)


async def emit_event(
    pool: asyncpg.Pool,
    ws_slug: str,
    event: str,
    doc_snapshot: dict[str, Any],
    *,
    encryption_key: str | None,
) -> None:
    """Fire-and-forget : à lancer via asyncio.create_task() après commit.

    Erreur → log structuré uniquement, jamais propagée.
    """
    try:
        async with pool.acquire() as conn:
            wk: uuid.UUID | None = await conn.fetchval(
                "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
            )
            if wk is None:
                return
            rows = await conn.fetch(
                "SELECT id, url, headers_encrypted FROM webhook_subscription "
                "WHERE workspace_technical_key = $1 AND active = true "
                "AND $2 = ANY(events)",
                wk,
                event,
            )
        if not rows:
            return
        payload: dict[str, Any] = {
            "event": event,
            "occurred_at": datetime.now(UTC).isoformat(),
            "workspace": ws_slug,
            "document": doc_snapshot,
        }
        async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
            for row in rows:
                doc_id = str(doc_snapshot.get("id", ""))
                url = row["url"].replace("{id_document}", doc_id)
                headers = _decrypt_safe(encryption_key, row["headers_encrypted"])
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                    log.info(
                        "webhook_sent",
                        webhook_id=str(row["id"]),
                        event=event,
                        status=resp.status_code,
                    )
                except Exception as exc:
                    log.warning(
                        "webhook_send_failed",
                        webhook_id=str(row["id"]),
                        event=event,
                        error=str(exc),
                    )
    except Exception as exc:
        log.error("webhook_emit_error", event=event, error=str(exc))

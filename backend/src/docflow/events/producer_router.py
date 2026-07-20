"""Router admin (superadmin) de la config du producteur d'events workflow.

Pilote à chaud l'émission : lecture/écriture de la config singleton, prise en
compte immédiate via `outbox.reconcile`, et test de connexion vers l'ingestion.
Le secret HMAC n'est jamais renvoyé (booléen `secret_configured` seulement).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from docflow.auth.deps import require_superadmin
from docflow.events import catalog, outbox, producer_config
from docflow.events.signing import SIGNATURE_HEADER, sign_body
from docflow.events.worker import _resolve_secret
from docflow.schemas.auth import AuthUser
from docflow.schemas.events_producer import EventsProducerConfigOut, EventsProducerConfigUpdate
from docflow.secrets.secret import Secret

log = structlog.get_logger(__name__)

router = APIRouter(tags=["events-producer"])
_SuperAdmin = Depends(require_superadmin)

# Poster injectable (url, corps brut, en-têtes) → code HTTP. Isole l'I/O réseau
# du test-connection pour les tests (monkeypatch de `_poster`).
Poster = Callable[[str, bytes, dict[str, str]], Awaitable[int]]

# eventCode HORS catalogue : le test-connection ne doit pas ressembler à un
# event métier ni transiter par l'outbox.
_TEST_EVENT_CODE = "docflow.testevent.v1"


async def _http_poster(url: str, body: bytes, headers: dict[str, str]) -> int:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(url, content=body, headers=headers, follow_redirects=False)
        return resp.status_code


# Point d'injection : les tests remplacent ce symbole par un poster factice.
_poster: Poster = _http_poster


def _to_out(cfg: dict[str, Any]) -> EventsProducerConfigOut:
    return EventsProducerConfigOut(
        enabled=cfg["enabled"],
        ingestion_url=cfg["ingestion_url"],
        source_id=cfg["source_id"],
        source_uri=cfg["source_uri"],
        allowed_events=list(cfg["allowed_events"]),
        secret_configured=cfg["secret_ref"] is not None,
    )


@router.get("/admin/events-producer", response_model=EventsProducerConfigOut)
async def get_producer_config(
    request: Request, _: AuthUser = _SuperAdmin
) -> EventsProducerConfigOut:
    cfg = await producer_config.get_config(request.app.state.pool)
    return _to_out(cfg)


@router.put("/admin/events-producer", response_model=EventsProducerConfigOut)
async def put_producer_config(
    body: EventsProducerConfigUpdate, request: Request, _: AuthUser = _SuperAdmin
) -> EventsProducerConfigOut:
    pool = request.app.state.pool
    cfg = await producer_config.update_config(pool, body.model_dump(exclude_unset=True))
    # Prise en compte à chaud immédiate (activation / source / allowlist).
    await outbox.reconcile(pool)
    return _to_out(cfg)


def _build_test_envelope(source: str) -> dict[str, Any]:
    """Enveloppe plate d'un event de test (hors catalogue), signable telle quelle."""
    return {
        "_eventId": str(uuid.uuid4()),
        "_eventCode": _TEST_EVENT_CODE,
        "_occurredAt": datetime.now(UTC).isoformat(),
        "_source": source,
        "_specVersion": catalog.SPEC_VERSION,
        "test": True,
    }


@router.post("/admin/events-producer/test-connection")
async def test_connection(request: Request, _: AuthUser = _SuperAdmin) -> dict[str, Any]:
    """Poste un event de test signé vers l'ingestion, sans passer par l'outbox."""
    pool = request.app.state.pool
    settings = request.app.state.settings
    cfg = await producer_config.get_config(pool)
    if not (cfg["ingestion_url"] and cfg["source_id"] and cfg["secret_ref"]):
        raise HTTPException(
            status_code=400,
            detail="config producteur incomplète (ingestion_url, source_id, secret_ref requis)",
        )
    secret = await _resolve_secret(Secret(cfg["secret_ref"]), pool=pool, settings=settings)
    envelope = _build_test_envelope(cfg["source_uri"])
    body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", SIGNATURE_HEADER: sign_body(secret, body)}
    url = f"{str(cfg['ingestion_url']).rstrip('/')}/events/{cfg['source_id']}"
    try:
        status = await _poster(url, body, headers)
    except Exception as exc:
        log.warning("events_producer_test_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"connexion échouée : {exc}") from exc
    return {"status": status, "ok": 200 <= status < 300}

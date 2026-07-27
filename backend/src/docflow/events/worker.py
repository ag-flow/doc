"""Worker de livraison de l'outbox d'events vers l'ingestion workflow.

Balaie périodiquement les events non envoyés, les signe (HMAC corps brut) et
les POST vers l'URL d'envoi complète (`ingestion_url`, collée depuis workflow).
Retry borné par backoff exponentiel ; l'`_eventId` (= id de ligne) est réutilisé tel
quel à chaque tentative → déduplication idempotente côté workflow.

Le claim utilise `FOR UPDATE SKIP LOCKED` + un bail (`next_attempt_at` poussé)
pour rester correct si plusieurs répliques tournent : deux workers ne prennent
jamais la même ligne.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
import httpx
import structlog

from docflow.events.signing import SIGNATURE_HEADER, sign_body

log = structlog.get_logger(__name__)

_HTTP_TIMEOUT = 10.0
_CLAIM_BATCH = 20
_BACKOFF_BASE = 30  # secondes
_BACKOFF_CAP = 3600  # 1 h
# Au-delà, l'event passe en dead-letter (failed_at) et n'est plus re-tenté :
# un event rejeté en permanence ne doit pas boucler indéfiniment.
MAX_ATTEMPTS = 8

# Poster injectable : (corps brut, en-têtes) → code HTTP. Isole l'I/O réseau
# pour les tests.
Poster = Callable[[bytes, dict[str, str]], Awaitable[int]]

# Claim atomique : sélectionne les events prêts, pose un bail de 60 s pour
# qu'une réplique concurrente ne les reprenne pas, et les retourne.
_CLAIM = """
UPDATE event_outbox SET next_attempt_at = now() + interval '60 seconds'
WHERE id IN (
    SELECT id FROM event_outbox
    WHERE sent_at IS NULL AND failed_at IS NULL AND next_attempt_at <= now()
    ORDER BY created_at
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, event_code, payload, attempts
"""


def _backoff_seconds(attempts: int) -> int:
    return int(min(_BACKOFF_BASE * (2**attempts), _BACKOFF_CAP))


async def _mark_sent(pool: asyncpg.Pool, event_id: uuid.UUID) -> None:
    await pool.execute(
        "UPDATE event_outbox SET sent_at = now(), last_error = NULL WHERE id = $1",
        event_id,
    )


async def _mark_failed(pool: asyncpg.Pool, event_id: uuid.UUID, attempts: int, error: str) -> None:
    new_attempts = attempts + 1
    if new_attempts >= MAX_ATTEMPTS:
        # Dead-letter : plus aucune tentative ; la ligne reste pour inspection.
        await pool.execute(
            "UPDATE event_outbox SET attempts = $2, failed_at = now(), last_error = $3 "
            "WHERE id = $1",
            event_id,
            new_attempts,
            error[:2000],
        )
        log.error("event_delivery_dead_letter", event_id=str(event_id), attempts=new_attempts)
        return
    delay = _backoff_seconds(attempts)
    await pool.execute(
        "UPDATE event_outbox SET attempts = $2, "
        "next_attempt_at = now() + make_interval(secs => $3), last_error = $4 "
        "WHERE id = $1",
        event_id,
        new_attempts,
        float(delay),
        error[:2000],
    )


async def purge_delivered(pool: asyncpg.Pool, *, older_than_hours: int) -> int:
    """Supprime les events LIVRÉS plus vieux que le seuil (rétention outbox).

    Les entrées dead-letter (`failed_at`) sont conservées pour inspection —
    seules les livraisons réussies sont purgées.
    """
    result = await pool.execute(
        "DELETE FROM event_outbox WHERE sent_at IS NOT NULL "
        "AND sent_at < now() - make_interval(hours => $1)",
        older_than_hours,
    )
    return int(result.split()[-1])


async def drain_once(
    pool: asyncpg.Pool, *, secret: str, poster: Poster, limit: int = _CLAIM_BATCH
) -> int:
    """Traite un lot d'events prêts. Retourne le nombre de lignes traitées."""
    rows = await pool.fetch(_CLAIM, limit)
    for row in rows:
        body: bytes = row["payload"].encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            SIGNATURE_HEADER: sign_body(secret, body),
        }
        try:
            status = await poster(body, headers)
        except Exception as exc:  # réseau, timeout…
            await _mark_failed(pool, row["id"], row["attempts"], str(exc))
            log.warning("event_delivery_failed", event_id=str(row["id"]), error=str(exc))
            continue
        if 200 <= status < 300:
            await _mark_sent(pool, row["id"])
            log.info("event_delivered", event_id=str(row["id"]), event_code=row["event_code"])
        else:
            await _mark_failed(pool, row["id"], row["attempts"], f"HTTP {status}")
            log.warning("event_delivery_rejected", event_id=str(row["id"]), status=status)
    return len(rows)


async def _resolve_secret(secret_obj: Any, *, pool: asyncpg.Pool, settings: Any) -> str:
    from docflow.secrets.resolver import resolve

    enc_key_obj = getattr(settings, "encryption_key", None)
    return await resolve(
        secret_obj,
        harpocrate_url=getattr(settings, "harpocrate_url", None),
        pool=pool,
        enc_key=enc_key_obj.reveal() if enc_key_obj is not None else None,
    )


def emission_configured(settings: Any) -> bool:
    """Émission seedable depuis l'env : les trois réglages workflow présents."""
    return bool(
        getattr(settings, "workflow_ingestion_url", None)
        and getattr(settings, "workflow_source_id", None)
        and getattr(settings, "workflow_hmac_secret", None)
    )


def _drainable(cfg: dict[str, Any]) -> bool:
    """La config DB permet-elle de draîner ? (activée + endpoint + secret posés)."""
    return bool(cfg["enabled"] and cfg["ingestion_url"] and cfg["secret_ref"])


async def worker_loop(pool: asyncpg.Pool, settings: Any) -> None:
    """Boucle de fond pilotée par la config DB (reconfiguration à chaud).

    À chaque tick : `outbox.reconcile` propage enabled/source/allowlist aux
    handlers web, puis on relit la config DB. Si elle est complète et activée,
    on draîne + purge ; sinon on reste au repos (aucun redémarrage requis).
    """
    from docflow.events import outbox, producer_config
    from docflow.secrets.secret import Secret

    tick = getattr(settings, "event_worker_tick_seconds", 15)
    purge_hours = getattr(settings, "event_outbox_purge_after_hours", 24)
    # Cache (ref, secret résolu) invalidé quand secret_ref change.
    secret_cache: tuple[str, str] | None = None
    # Endpoint courant (réaffecté à chaque tick) — poster défini une seule fois
    # hors boucle pour ne pas capturer une variable de boucle (B023).
    endpoint = ""

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:

        async def poster(body: bytes, headers: dict[str, str]) -> int:
            resp = await client.post(endpoint, content=body, headers=headers)
            return resp.status_code

        log.info("event_worker_started")
        while True:
            try:
                await outbox.reconcile(pool)
                cfg = await producer_config.get_config(pool)
                if _drainable(cfg):
                    # ingestion_url = l'URL d'envoi COMPLÈTE (à coller depuis
                    # workflow) : on POST directement dessus, aucun ajout.
                    endpoint = str(cfg["ingestion_url"])
                    ref: str = cfg["secret_ref"]
                    if secret_cache is None or secret_cache[0] != ref:
                        resolved = await _resolve_secret(Secret(ref), pool=pool, settings=settings)
                        secret_cache = (ref, resolved)
                    await drain_once(pool, secret=secret_cache[1], poster=poster)
                    await purge_delivered(pool, older_than_hours=purge_hours)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("event_worker_error", error=str(exc))
            await asyncio.sleep(tick)

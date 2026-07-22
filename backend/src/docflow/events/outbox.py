"""Écriture des events dans l'outbox transactionnel (contrat producteur workflow).

`enqueue` s'appelle DANS la transaction de la mutation métier : l'event et la
mutation sont atomiques. Aucun envoi réseau ici — le worker (events/worker.py)
pousse ensuite les lignes non envoyées.

L'émission est gouvernée par un drapeau de module posé au démarrage
(`configure`) à partir des Settings : si le workflow n'est pas configuré,
`enqueue` est un no-op (aucune ligne écrite, aucune croissance de l'outbox).
Miroir du patron `mcp.server.configure`.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
import structlog

from docflow.events import catalog

log = structlog.get_logger(__name__)

# Champs système de l'enveloppe (norme §2.3) — liste fixe et fermée.
_SYSTEM_FIELDS = frozenset(
    {"_eventId", "_eventCode", "_occurredAt", "_source", "_specVersion", "_traceId"}
)

_enabled: bool = False
_source: str = "docflow"
# Allowlist des eventCodes relayés. None = « tous autorisés » (rétro-compat :
# un appel à `configure` sans `allowed_events` ne filtre pas). Un set explicite
# (posé par `reconcile` depuis la config DB) applique le fail-closed : un set
# vide relaie zéro event.
_allowed_events: set[str] | None = None


def configure(*, enabled: bool, source: str, allowed_events: set[str] | None = None) -> None:
    global _enabled, _source, _allowed_events
    _enabled = enabled
    _source = source
    _allowed_events = allowed_events


def is_enabled() -> bool:
    return _enabled


async def reconcile(pool: asyncpg.Pool) -> None:
    """Reconfigure l'émission depuis la config DB (activation, source, allowlist).

    Appelé au boot et à chaque tick du worker : propage aux handlers web l'état
    piloté en admin. Pose TOUJOURS une allowlist explicite (set) → fail-closed.
    """
    from docflow.events import producer_config

    cfg = await producer_config.get_config(pool)
    configure(
        enabled=cfg["enabled"],
        source=cfg["source_uri"],
        allowed_events=set(cfg["allowed_events"]),
    )


def build_envelope(
    event_id: uuid.UUID,
    event_code: str,
    occurred_at: datetime,
    source: str,
    business: dict[str, Any],
) -> dict[str, Any]:
    """Assemble l'enveloppe plate : champs système + champs métier à la racine.

    Refuse un champ métier dont le nom empiète sur la liste système (norme §2.2).
    """
    collisions = _SYSTEM_FIELDS & business.keys()
    if collisions:
        raise ValueError(f"champ métier en collision avec un champ système : {sorted(collisions)}")
    return {
        "_eventId": str(event_id),
        "_eventCode": event_code,
        "_occurredAt": occurred_at.isoformat(),
        "_source": source,
        "_specVersion": catalog.SPEC_VERSION,
        **business,
    }


# Namespace stable pour les `_eventId` déterministes (uuid5). Fixe : ne jamais
# changer, sinon la dédup côté workflow perdrait la corrélation historique.
_EVENT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:yoops:docflow:events")


def _event_id(event_code: str, dedup_key: str | None) -> uuid.UUID:
    """`_eventId` déterministe (uuid5) si une clé de dédup est fournie, sinon aléatoire.

    Déterministe = un rejeu du même changement logique porte le même id : la
    dédup côté workflow joue, et l'INSERT `ON CONFLICT DO NOTHING` évite le
    double-enqueue producteur. À réserver aux events dont la clé est
    naturellement unique/monotone (création, suppression, version) — pour un
    event répétable sans discriminant (déplacement, retypage), laisser
    `dedup_key=None` (aléatoire) afin de NE PAS écraser une transition légitime.
    """
    if dedup_key is None:
        return uuid.uuid4()
    return uuid.uuid5(_EVENT_NAMESPACE, f"{event_code}|{dedup_key}")


def _as_uuid(value: Any) -> uuid.UUID | None:
    """Parse un uuid string tolérant (None si absent/invalide)."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


async def _record_document_event(
    conn: asyncpg.Connection,
    event_code: str,
    workspace_wk: uuid.UUID | None,
    business: dict[str, Any],
) -> None:
    """Journal DURABLE de l'event (consommé par les automates).

    Écrit TOUJOURS, indépendamment de l'émission workflow externe (activation /
    allowlist) : les automates internes ne doivent pas dépendre du producteur.
    """
    await conn.execute(
        "INSERT INTO document_event "
        "(workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1, $2, $3, $4::jsonb)",
        workspace_wk,
        _as_uuid(business.get("documentId")),
        event_code,
        json.dumps(business, ensure_ascii=False),
    )


async def enqueue(
    conn: asyncpg.Connection,
    *,
    event_code: str,
    workspace_wk: uuid.UUID | None,
    business: dict[str, Any],
    dedup_key: str | None = None,
) -> None:
    """Écrit un event : journal durable `document_event` PUIS outbox producteur.

    Le journal `document_event` est écrit inconditionnellement (source des
    automates). L'écriture outbox (émission workflow externe) reste gouvernée
    par l'activation + l'allowlist fail-closed. Ne lève jamais pour un eventCode
    hors catalogue : code inconnu = bug producteur, journalisé, pas propagé.

    `dedup_key` (optionnel) rend `_eventId` déterministe (uuid5) : un ré-enqueue
    du même changement logique est absorbé par `ON CONFLICT DO NOTHING` (dédup
    producteur), sans jamais faire échouer la mutation.
    """
    if not catalog.is_known(event_code):
        log.warning("event_code_unknown", event_code=event_code)
        return
    # 1) Journal durable des events (automates) — toujours.
    await _record_document_event(conn, event_code, workspace_wk, business)
    # 2) Outbox producteur workflow — gated (activation + allowlist).
    if not _enabled:
        return
    if _allowed_events is not None and event_code not in _allowed_events:
        return
    event_id = _event_id(event_code, dedup_key)
    occurred_at = datetime.now(UTC)
    envelope = build_envelope(event_id, event_code, occurred_at, _source, business)
    await conn.execute(
        "INSERT INTO event_outbox (id, event_code, workspace_technical_key, payload, occurred_at) "
        "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
        event_id,
        event_code,
        workspace_wk,
        json.dumps(envelope, ensure_ascii=False),
        occurred_at,
    )

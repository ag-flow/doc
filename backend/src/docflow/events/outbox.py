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


def configure(*, enabled: bool, source: str) -> None:
    global _enabled, _source
    _enabled = enabled
    _source = source


def is_enabled() -> bool:
    return _enabled


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


async def enqueue(
    conn: asyncpg.Connection,
    *,
    event_code: str,
    workspace_wk: uuid.UUID | None,
    business: dict[str, Any],
    dedup_key: str | None = None,
) -> None:
    """Écrit un event dans l'outbox (dans la transaction courante).

    No-op si l'émission est désactivée. Ne lève jamais pour un eventCode hors
    catalogue : on ne publie que des events déclarés dans la découverte — un
    code inconnu est un bug producteur, journalisé, pas propagé à la mutation.

    `dedup_key` (optionnel) rend `_eventId` déterministe (uuid5) : un ré-enqueue
    du même changement logique est absorbé par `ON CONFLICT DO NOTHING` (dédup
    producteur), sans jamais faire échouer la mutation.
    """
    if not _enabled:
        return
    if not catalog.is_known(event_code):
        log.warning("event_code_unknown", event_code=event_code)
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

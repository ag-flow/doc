"""Flux SSE d'un document : signal léger « quelque chose a changé ».

Source du signal : le journal durable ``document_event`` — alimenté par TOUS
les chemins d'écriture (REST, MCP, automates). Le flux surveille les seq
nouveaux du document (boucle courte, connexions courtes : aucune connexion du
pool n'est retenue entre deux sondes) et pousse un payload minimal
``{document_id, version, updated_at, updated_by}`` — jamais le contenu.

Contrat SSE :
- un événement ``change`` est émis IMMÉDIATEMENT à la connexion (état courant,
  sert de test de vie au client) ;
- un commentaire keep-alive part toutes les ~30 s sans activité ;
- un document supprimé en cours de flux émet ``gone`` puis termine.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace

POLL_SECONDS = 2.0
KEEPALIVE_SECONDS = 30.0

_DOC_STATE = (
    "SELECT d.version, d.updated_at, d.updated_by "
    "FROM document d "
    "WHERE d.doc_technical_key = $1 AND d.workspace_technical_key = $2"
)


async def ensure_document(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID
) -> uuid.UUID:
    """404 AVANT d'ouvrir le flux ; retourne la clé du workspace."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        exists = await conn.fetchval(
            "SELECT 1 FROM document WHERE doc_technical_key = $1 "
            "AND workspace_technical_key = $2",
            doc_id,
            wk,
        )
    if not exists:
        raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
    return wk


def _sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


async def _state_event(
    pool: asyncpg.Pool, wk: uuid.UUID, doc_id: uuid.UUID
) -> str | None:
    """Événement `change` avec l'état courant ; None si le document a disparu."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_DOC_STATE, doc_id, wk)
    if row is None:
        return None
    return _sse(
        "change",
        {
            "document_id": str(doc_id),
            "version": row["version"],
            "updated_at": row["updated_at"],
            "updated_by": row["updated_by"],
        },
    )


async def stream_document(
    pool: asyncpg.Pool,
    wk: uuid.UUID,
    doc_id: uuid.UUID,
    *,
    poll_seconds: float = POLL_SECONDS,
    keepalive_seconds: float = KEEPALIVE_SECONDS,
) -> AsyncIterator[str]:
    """Générateur SSE. S'arrête proprement à la déconnexion (CancelledError)
    ou quand le document disparaît."""
    async with pool.acquire() as conn:
        last_seq: int = (
            await conn.fetchval(
                "SELECT COALESCE(max(seq), 0) FROM document_event WHERE document_ref = $1",
                doc_id,
            )
            or 0
        )

    initial = await _state_event(pool, wk, doc_id)
    if initial is None:
        yield _sse("gone", {"document_id": str(doc_id)})
        return
    yield initial

    idle = 0.0
    while True:
        await asyncio.sleep(poll_seconds)
        idle += poll_seconds
        async with pool.acquire() as conn:
            max_seq: int = (
                await conn.fetchval(
                    "SELECT COALESCE(max(seq), 0) FROM document_event "
                    "WHERE document_ref = $1",
                    doc_id,
                )
                or 0
            )
        if max_seq > last_seq:
            last_seq = max_seq
            idle = 0.0
            event = await _state_event(pool, wk, doc_id)
            if event is None:
                yield _sse("gone", {"document_id": str(doc_id)})
                return
            yield event
        elif idle >= keepalive_seconds:
            idle = 0.0
            yield ": keepalive\n\n"

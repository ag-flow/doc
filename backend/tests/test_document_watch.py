"""Flux SSE /documents/{id}/watch — signal minimal, jamais le contenu."""

from __future__ import annotations

import asyncio
import json
import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import watch


async def _seed(pool: asyncpg.Pool) -> tuple[str, uuid.UUID, uuid.UUID]:
    slug = f"watch-{uuid.uuid4().hex[:8]}"
    async with pool.acquire() as conn:
        wk = await conn.fetchval(
            "INSERT INTO workspace (slug, label) VALUES ($1, 'Watch WS') "
            "RETURNING workspace_technical_key",
            slug,
        )
        type_id = await conn.fetchval(
            "INSERT INTO functional_type (slug, label, workspace_technical_key) "
            "VALUES ('page', 'Page', $1) RETURNING id",
            wk,
        )
        block_id = await conn.fetchval(
            "INSERT INTO data_block (slug, label, functional_type_ref, "
            "workspace_technical_key) VALUES ('blk', 'Bloc', $1, $2) RETURNING id",
            type_id,
            wk,
        )
        doc_id = await conn.fetchval(
            "INSERT INTO document (title, workspace_technical_key, functional_type_ref, "
            "data_block_ref, updated_by) VALUES ('Doc', $1, $2, $3, 'seed') "
            "RETURNING doc_technical_key",
            wk,
            type_id,
            block_id,
        )
    return slug, wk, doc_id


def _parse(sse: str) -> tuple[str, dict[str, object]]:
    lines = sse.strip().split("\n")
    event = lines[0].removeprefix("event: ")
    data = json.loads(lines[1].removeprefix("data: "))
    return event, data


async def test_ensure_document_404(db_pool: asyncpg.Pool) -> None:
    slug, _, _ = await _seed(db_pool)
    with pytest.raises(HTTPException) as exc:
        await watch.ensure_document(db_pool, slug, uuid.uuid4())
    assert exc.value.status_code == 404


async def test_stream_initial_change_then_signal_then_gone(db_pool: asyncpg.Pool) -> None:
    slug, wk, doc_id = await _seed(db_pool)
    gen = watch.stream_document(db_pool, wk, doc_id, poll_seconds=0.05)

    # 1. État courant émis immédiatement à la connexion (test de vie).
    event, data = _parse(await asyncio.wait_for(gen.__anext__(), timeout=2))
    assert event == "change"
    assert data["document_id"] == str(doc_id)
    assert data["version"] == 1
    assert data["updated_by"] == "seed"

    # 2. Une écriture backend (journal document_event + bump de version) est vue.
    await db_pool.execute(
        "UPDATE document SET version = 2, updated_by = 'agent' WHERE doc_technical_key = $1",
        doc_id,
    )
    await db_pool.execute(
        "INSERT INTO document_event (workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1, $2, 'docflow.document.updated.v1', '{}'::jsonb)",
        wk,
        doc_id,
    )
    event, data = _parse(await asyncio.wait_for(gen.__anext__(), timeout=2))
    assert event == "change"
    assert data["version"] == 2
    assert data["updated_by"] == "agent"
    # Signal minimal : jamais le contenu.
    assert "content" not in data and "contenu" not in data

    # 3. Document supprimé pendant le flux → `gone` puis fin.
    await db_pool.execute(
        "INSERT INTO document_event (workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1, $2, 'docflow.document.deleted.v1', '{}'::jsonb)",
        wk,
        doc_id,
    )
    await db_pool.execute("DELETE FROM document WHERE doc_technical_key = $1", doc_id)
    event, data = _parse(await asyncio.wait_for(gen.__anext__(), timeout=2))
    assert event == "gone"
    await gen.aclose()


async def test_stream_keepalive_when_idle(db_pool: asyncpg.Pool) -> None:
    slug, wk, doc_id = await _seed(db_pool)
    gen = watch.stream_document(
        db_pool, wk, doc_id, poll_seconds=0.02, keepalive_seconds=0.04
    )
    first = await asyncio.wait_for(gen.__anext__(), timeout=2)
    assert first.startswith("event: change")
    second = await asyncio.wait_for(gen.__anext__(), timeout=2)
    assert second.startswith(": keepalive")
    await gen.aclose()

"""Concurrence des reparentages (niveau 1 de la défense anti-cycle).

Deux transactions READ COMMITTED qui reparentent A→B et B→A en même temps
passaient chacune la validation anti-cycle (check-then-act) et créaient un
cycle. Le verrou consultatif transactionnel sérialise la validation : une
des deux opérations doit échouer en 422.

La barrière est injectée ENTRE la validation et l'UPDATE (monkeypatch du
validateur) pour garantir que les deux transactions sont ouvertes et validées
simultanément — le timeout tolère le cas post-fix où la seconde transaction
reste bloquée sur le verrou et n'atteint jamais la barrière.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.schemas.document import DocumentCreate, DocumentUpdate
from docflow.schemas.types import FunctionalTypeCreate, FunctionalTypeUpdate
from docflow.types import service as type_svc

_WS = "test-ws"

_Check = Callable[[asyncpg.Connection, uuid.UUID, uuid.UUID], Awaitable[None]]


def _barrier_after_check(real: _Check, barrier: asyncio.Barrier) -> _Check:
    async def wrapped(
        conn: asyncpg.Connection, node_id: uuid.UUID, proposed_parent_id: uuid.UUID
    ) -> None:
        await real(conn, node_id, proposed_parent_id)
        try:
            await asyncio.wait_for(barrier.wait(), timeout=1.5)
        except TimeoutError:
            pass

    return wrapped


async def test_concurrent_document_reparent_cannot_create_cycle(
    db_pool: asyncpg.Pool,
    test_workspace: dict,
    test_block: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_a = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc A", block_id=test_block["id"])
    )
    doc_b = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc B", block_id=test_block["id"])
    )
    a, b = doc_a.doc_technical_key, doc_b.doc_technical_key

    barrier = asyncio.Barrier(2)
    monkeypatch.setattr(
        doc_svc,
        "_check_no_document_cycle",
        _barrier_after_check(doc_svc._check_no_document_cycle, barrier),
    )

    async def reparent(child: uuid.UUID, parent: uuid.UUID) -> HTTPException | None:
        try:
            await doc_svc.update_document(db_pool, _WS, child, DocumentUpdate(parent_id=parent))
        except HTTPException as exc:
            return exc
        return None

    async with asyncio.timeout(10):
        results = await asyncio.gather(reparent(a, b), reparent(b, a))

    rows = await db_pool.fetch(
        "SELECT doc_technical_key, parent FROM document WHERE doc_technical_key = ANY($1::uuid[])",
        [a, b],
    )
    parents = {r["doc_technical_key"]: r["parent"] for r in rows}
    assert not (parents[a] == b and parents[b] == a), "cycle A<->B créé par la course"

    errors = [r for r in results if r is not None]
    assert len(errors) == 1
    assert errors[0].status_code == 422


async def test_concurrent_type_reparent_cannot_create_cycle(
    db_pool: asyncpg.Pool,
    test_workspace: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="race-a", label="Race A"))
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="race-b", label="Race B"))

    barrier = asyncio.Barrier(2)
    monkeypatch.setattr(
        type_svc,
        "_check_no_cycle",
        _barrier_after_check(type_svc._check_no_cycle, barrier),
    )

    async def reparent(child_slug: str, parent_slug: str) -> HTTPException | None:
        try:
            await type_svc.update_type(
                db_pool, _WS, child_slug, FunctionalTypeUpdate(parent_slug=parent_slug)
            )
        except HTTPException as exc:
            return exc
        return None

    async with asyncio.timeout(10):
        results = await asyncio.gather(reparent("race-a", "race-b"), reparent("race-b", "race-a"))

    rows = await db_pool.fetch(
        "SELECT ft.slug, p.slug AS parent_slug "
        "FROM functional_type ft LEFT JOIN functional_type p ON p.id = ft.parent "
        "WHERE ft.workspace_technical_key = $1 AND ft.slug = ANY($2::text[])",
        test_workspace["workspace_technical_key"],
        ["race-a", "race-b"],
    )
    parents = {r["slug"]: r["parent_slug"] for r in rows}
    assert not (parents["race-a"] == "race-b" and parents["race-b"] == "race-a"), (
        "cycle race-a<->race-b créé par la course"
    )

    errors = [r for r in results if r is not None]
    assert len(errors) == 1
    assert errors[0].status_code == 422

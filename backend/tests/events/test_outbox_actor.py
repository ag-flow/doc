"""Fondation OBO sortant (Task 1) : `document_event` porte le GUID de l'acteur.

Un worker asynchrone doit pouvoir relayer l'identité de l'acteur qui a
déclenché la mutation (OBO) — il faut donc que le journal durable des events
la porte, puisque c'est l'unique source que le worker consulte.
"""

from __future__ import annotations

import uuid

import asyncpg

from docflow.events import outbox
from docflow.observability import correlation as corr


async def test_enqueue_persiste_actor_guid_du_contexte_ambiant(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    wk = test_workspace["workspace_technical_key"]
    doc_key = uuid.uuid4()
    actor_guid = "11111111-1111-1111-1111-111111111111"
    ctx = corr.new_document_context(doc_key, actor_guid=actor_guid)
    token = corr.bind(ctx)
    try:
        async with db_pool.acquire() as conn, conn.transaction():
            await outbox.enqueue(
                conn,
                event_code="docflow.document.created.v1",
                workspace_wk=wk,
                business={"documentId": str(doc_key)},
            )
    finally:
        corr.reset(token)

    row = await db_pool.fetchrow(
        "SELECT actor_guid FROM document_event WHERE document_ref=$1", doc_key
    )
    assert row is not None
    assert row["actor_guid"] == actor_guid

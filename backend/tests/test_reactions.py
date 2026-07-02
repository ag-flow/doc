"""Régression : reactions/service.py référençait admin_user (renommé app_user en 0027)."""
from __future__ import annotations

import uuid

import asyncpg

from docflow.documents import service as doc_svc
from docflow.reactions import service as react_svc
from docflow.schemas.document import DocumentCreate

_WS = "test-ws"


async def _make_user(pool: asyncpg.Pool, email: str, label: str) -> uuid.UUID:
    user_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO app_user (username, email, label, is_admin, validated, source) "
        "VALUES ($1, $2, $3, false, true, 'local') RETURNING id",
        email, email, label,
    )
    return user_id


async def test_doc_reaction_summary_joins_app_user(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc", block_id=test_block["id"])
    )
    user_id = await _make_user(db_pool, "liker@example.com", "Liker")

    summary = await react_svc.toggle_doc_reaction(
        db_pool, _WS, doc.doc_technical_key, user_id, 1
    )
    assert summary.likes == 1
    assert summary.dislikes == 0
    assert summary.my_reaction == 1
    assert summary.last_likes == ["Liker"]


async def test_comment_summary_joins_app_user(
    db_pool: asyncpg.Pool, test_workspace: dict, test_block: dict
) -> None:
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="Doc", block_id=test_block["id"])
    )
    user_id = await _make_user(db_pool, "author@example.com", "Author")

    comment = await react_svc.add_comment(
        db_pool, _WS, doc.doc_technical_key, user_id, "Author", "Un commentaire"
    )
    assert comment.author_label == "Author"

    comments = await react_svc.list_comments(db_pool, _WS, doc.doc_technical_key, user_id)
    assert len(comments) == 1
    assert comments[0].author_label == "Author"

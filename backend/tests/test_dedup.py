"""Tests de la clef de dédoublonnage (sha256 d'une clef texte normalisée)."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import dedup


def test_normalize_and_hash_trims_and_lowercases() -> None:
    # trim + minuscules : ces variantes doivent produire le MÊME sha256.
    base = dedup.normalize_and_hash("hello world")
    assert dedup.normalize_and_hash("  Hello World  ") == base
    assert dedup.normalize_and_hash("HELLO WORLD") == base
    # empreinte attendue = sha256 de la forme normalisée
    assert base == hashlib.sha256(b"hello world").hexdigest()


async def _seed_doc(
    db_pool: asyncpg.Pool, ws_key: uuid.UUID, block_id: uuid.UUID, type_id: uuid.UUID, title: str
) -> uuid.UUID:
    doc_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO document "
        "(title, functional_type_ref, workspace_technical_key, data_block_ref) "
        "VALUES ($1, $2, $3, $4) RETURNING doc_technical_key",
        title,
        type_id,
        ws_key,
        block_id,
    )
    return doc_id


@pytest.fixture
async def dedup_ws(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> AsyncIterator[dict[str, object]]:
    ws_key: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    type_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ('note', 'Note', $1) RETURNING id",
        ws_key,
    )
    block_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ('notes', 'Notes', $1, $2) RETURNING id",
        type_id,
        ws_key,
    )
    # Le teardown de test_workspace supprime le workspace en cascade.
    yield {"ws_key": ws_key, "type_id": type_id, "block_id": block_id}


async def test_set_then_find_normalized(db_pool: asyncpg.Pool, dedup_ws: dict[str, object]) -> None:
    doc = await _seed_doc(
        db_pool, dedup_ws["ws_key"], dedup_ws["block_id"], dedup_ws["type_id"], "Doc A"
    )
    out = await dedup.set_dedup_key(db_pool, "test-ws", doc, "  Clef-ABC ")
    assert out["updated"] is True
    assert out["dedup_sha256"] == hashlib.sha256(b"clef-abc").hexdigest()

    # Recherche avec une casse/espaces différents : la normalisation doit matcher.
    found = await dedup.find_by_dedup_key(db_pool, "test-ws", "CLEF-ABC")
    assert found["total"] == 1
    assert found["documents"][0]["id"] == str(doc)

    # Une autre clef ne retourne rien.
    assert (await dedup.find_by_dedup_key(db_pool, "test-ws", "autre"))["total"] == 0


async def test_multiple_documents_same_key_allowed(
    db_pool: asyncpg.Pool, dedup_ws: dict[str, object]
) -> None:
    # Non-unicité : deux documents peuvent porter la même clef (décision de
    # l'appelant), l'application ne l'empêche pas.
    a = await _seed_doc(db_pool, dedup_ws["ws_key"], dedup_ws["block_id"], dedup_ws["type_id"], "A")
    b = await _seed_doc(db_pool, dedup_ws["ws_key"], dedup_ws["block_id"], dedup_ws["type_id"], "B")
    await dedup.set_dedup_key(db_pool, "test-ws", a, "meme-clef")
    await dedup.set_dedup_key(db_pool, "test-ws", b, "MEME-CLEF")
    found = await dedup.find_by_dedup_key(db_pool, "test-ws", " meme-clef ")
    assert found["total"] == 2
    assert {d["id"] for d in found["documents"]} == {str(a), str(b)}  # type: ignore[index]


async def test_empty_text_clears_key(db_pool: asyncpg.Pool, dedup_ws: dict[str, object]) -> None:
    doc = await _seed_doc(
        db_pool, dedup_ws["ws_key"], dedup_ws["block_id"], dedup_ws["type_id"], "C"
    )
    await dedup.set_dedup_key(db_pool, "test-ws", doc, "clef")
    assert (await dedup.find_by_dedup_key(db_pool, "test-ws", "clef"))["total"] == 1
    # Texte vide → efface (null) ; None aussi.
    cleared = await dedup.set_dedup_key(db_pool, "test-ws", doc, "   ")
    assert cleared["dedup_sha256"] is None
    assert (await dedup.find_by_dedup_key(db_pool, "test-ws", "clef"))["total"] == 0


async def test_set_unknown_document_404(db_pool: asyncpg.Pool, dedup_ws: dict[str, object]) -> None:
    with pytest.raises(HTTPException) as exc:
        await dedup.set_dedup_key(db_pool, "test-ws", uuid.uuid4(), "x")
    assert exc.value.status_code == 404

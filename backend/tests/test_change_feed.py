from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import pytest

from docflow.documents import service as doc_svc
from docflow.schemas.document import DocumentCreate, DocumentUpdate
from docflow.schemas.property_value import PropertyValueSet


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
async def cf_ws(db_pool: asyncpg.Pool) -> Any:
    row = await db_pool.fetchrow(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) "
        "RETURNING workspace_technical_key, slug",
        "cf-ws", "Change Feed WS",
    )
    assert row is not None
    yield dict(row)
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "cf-ws")


@pytest.fixture()
async def cf_block(db_pool: asyncpg.Pool, cf_ws: dict[str, Any]) -> Any:
    wk = cf_ws["workspace_technical_key"]
    t = await db_pool.fetchrow(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ('cf-type', 'CF Type', $1) RETURNING id",
        wk,
    )
    assert t is not None
    b = await db_pool.fetchrow(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ('cf-block', 'CF Block', $1, $2) RETURNING id",
        t["id"], wk,
    )
    assert b is not None
    yield {"block_id": b["id"], "type_id": t["id"]}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _changes(
    db_pool: asyncpg.Pool, ws_slug: str, since: int = 0, limit: int = 100
) -> list[dict[str, Any]]:
    wk = await db_pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
    )
    rows = await db_pool.fetch(
        "SELECT seq, nature, document_ref FROM document_change_log "
        "WHERE workspace_technical_key = $1 AND seq > $2 ORDER BY seq LIMIT $3",
        wk, since, limit,
    )
    return [dict(r) for r in rows]


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_create_logs_C(db_pool: asyncpg.Pool, cf_ws: dict[str, Any], cf_block: dict[str, Any]) -> None:
    """DoD 30 — création → nature C dans le journal."""
    doc = await doc_svc.create_document(
        db_pool, "cf-ws",
        DocumentCreate(title="Doc C", block_id=cf_block["block_id"], functional_type_slug="cf-type"),
    )
    changes = await _changes(db_pool, "cf-ws")
    assert any(c["nature"] == "C" and c["document_ref"] == doc.doc_technical_key for c in changes)


async def test_update_content_logs_U(
    db_pool: asyncpg.Pool, cf_ws: dict[str, Any], cf_block: dict[str, Any]
) -> None:
    """DoD 30 — modification contenu → nature U."""
    doc = await doc_svc.create_document(
        db_pool, "cf-ws",
        DocumentCreate(title="Doc U", block_id=cf_block["block_id"], functional_type_slug="cf-type"),
    )
    before = await _changes(db_pool, "cf-ws")
    last_seq = max(c["seq"] for c in before)

    await doc_svc.update_document(
        db_pool, "cf-ws", doc.doc_technical_key,
        DocumentUpdate(title="Doc U v2", expected_version=1),
    )
    changes_after = await _changes(db_pool, "cf-ws", since=last_seq)
    assert any(c["nature"] == "U" for c in changes_after)


async def test_delete_logs_D_and_survives(
    db_pool: asyncpg.Pool, cf_ws: dict[str, Any], cf_block: dict[str, Any]
) -> None:
    """DoD 30 — suppression → nature D ; la ligne survit à l'absence du document."""
    doc = await doc_svc.create_document(
        db_pool, "cf-ws",
        DocumentCreate(title="Doc D", block_id=cf_block["block_id"], functional_type_slug="cf-type"),
    )
    doc_id = doc.doc_technical_key
    before = await _changes(db_pool, "cf-ws")
    last_seq = max(c["seq"] for c in before)

    await doc_svc.delete_document(db_pool, "cf-ws", doc_id)

    changes_after = await _changes(db_pool, "cf-ws", since=last_seq)
    d_entries = [c for c in changes_after if c["nature"] == "D" and c["document_ref"] == doc_id]
    assert d_entries, "Ligne D absente du journal"

    # Le document n'existe plus
    exists = await db_pool.fetchval(
        "SELECT doc_technical_key FROM document WHERE doc_technical_key = $1", doc_id
    )
    assert exists is None
    # Mais la ligne D est toujours là
    still_there = await db_pool.fetchval(
        "SELECT seq FROM document_change_log WHERE document_ref = $1 AND nature = 'D'", doc_id
    )
    assert still_there is not None


async def test_change_feed_order_and_pagination(
    db_pool: asyncpg.Pool, cf_ws: dict[str, Any], cf_block: dict[str, Any]
) -> None:
    """DoD 30 — ordre total + pagination sans doublon ni trou."""
    # Baseline seq
    baseline = await _changes(db_pool, "cf-ws")
    since0 = max((c["seq"] for c in baseline), default=0)

    # Créer 3 documents
    docs = []
    for i in range(3):
        d = await doc_svc.create_document(
            db_pool, "cf-ws",
            DocumentCreate(
                title=f"Pag {i}", block_id=cf_block["block_id"], functional_type_slug="cf-type"
            ),
        )
        docs.append(d)

    # Page 1 : limit=2
    p1 = await _changes(db_pool, "cf-ws", since=since0, limit=2)
    assert len(p1) == 2
    assert p1[0]["seq"] < p1[1]["seq"]

    # Page 2 : since = dernier seq de p1
    since1 = p1[-1]["seq"]
    p2 = await _changes(db_pool, "cf-ws", since=since1, limit=2)
    assert len(p2) >= 1
    # Pas de doublon
    all_seqs = [c["seq"] for c in p1 + p2]
    assert len(all_seqs) == len(set(all_seqs))
    # Pas de trou (ordre strict croissant)
    for a, b in zip(all_seqs, all_seqs[1:]):
        assert a < b


async def test_set_property_value_logs_P(
    db_pool: asyncpg.Pool, cf_ws: dict[str, Any], cf_block: dict[str, Any]
) -> None:
    """DoD 30 — mise à jour valeur propriété → nature P."""
    from docflow.schemas.property import PropertiesDefCreate
    from docflow.properties import service as prop_svc

    wk = cf_ws["workspace_technical_key"]
    # Ajouter une propriété text au type
    await prop_svc.create_property_def(
        db_pool, "cf-ws", "cf-type",
        PropertiesDefCreate(slug="notes", label="Notes", type="text"),
    )

    doc = await doc_svc.create_document(
        db_pool, "cf-ws",
        DocumentCreate(title="PropDoc", block_id=cf_block["block_id"], functional_type_slug="cf-type"),
    )
    before = await _changes(db_pool, "cf-ws")
    last_seq = max(c["seq"] for c in before)

    await doc_svc.set_property_value(
        db_pool, "cf-ws", doc.doc_technical_key, "notes",
        PropertyValueSet(value="hello", expected_version=0),
    )
    changes_after = await _changes(db_pool, "cf-ws", since=last_seq)
    assert any(c["nature"] == "P" for c in changes_after)

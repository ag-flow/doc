from __future__ import annotations

import json

import asyncpg
import pytest

from docflow.documents import block_ops
from docflow.documents import service as doc_svc
from docflow.events import catalog, outbox
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreate, DocumentCreateInBlock, DocumentUpdate
from docflow.schemas.properties import PropertiesDefCreate
from docflow.schemas.property_value import PropertyValueSet
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


@pytest.fixture()
async def emit(db_pool: asyncpg.Pool):  # type: ignore[no-untyped-def]
    """Active l'émission d'events et isole l'outbox pour le test."""
    await db_pool.execute("DELETE FROM event_outbox")
    outbox.configure(enabled=True, source="docflow-test")
    yield
    outbox.configure(enabled=False, source="docflow")
    await db_pool.execute("DELETE FROM event_outbox")


async def _events(pool: asyncpg.Pool) -> list[tuple[str, dict]]:
    rows = await pool.fetch("SELECT event_code, payload FROM event_outbox ORDER BY created_at")
    return [(r["event_code"], json.loads(r["payload"])) for r in rows]


# ── Catalogue & enveloppe (unitaire, sans DB) ─────────────────────────────────


def test_catalog_shape() -> None:
    assert len(catalog.CATALOG) == 6
    assert catalog.catalog_revision().startswith("sha256:")
    codes = {e["eventCode"] for e in catalog.catalog_summary()}
    assert "docflow.document.created.v1" in codes
    assert "docflow.document.propertyChanged.v1" in codes


def test_get_schema_known_and_unknown() -> None:
    s = catalog.get_schema("docflow.document.created.v1", 1)
    assert s is not None
    assert s["version"] == 1
    assert s["dataSchema"]["required"] == ["documentId", "workspaceSlug", "blockSlug", "title"]
    assert s["hash"].startswith("sha256:")
    assert catalog.get_schema("docflow.document.created.v1", 2) is None
    assert catalog.get_schema("docflow.inconnu.v1", 1) is None
    assert catalog.list_versions("docflow.document.created.v1") == [1]
    assert catalog.list_versions("docflow.inconnu.v1") is None


async def test_enqueue_deterministic_id_and_dedup(
    db_pool: asyncpg.Pool, test_workspace: dict, emit: None
) -> None:
    # Avec dedup_key : _eventId = uuid5 stable, et un ré-enqueue du même
    # changement logique est absorbé (ON CONFLICT DO NOTHING) → une seule ligne.
    import uuid

    wk = test_workspace["workspace_technical_key"]
    doc = uuid.uuid4()

    async def _push() -> None:
        async with db_pool.acquire() as conn, conn.transaction():
            await outbox.enqueue(
                conn,
                event_code="docflow.document.created.v1",
                workspace_wk=wk,
                business={"documentId": str(doc)},
                dedup_key=str(doc),
            )

    await _push()
    await _push()
    rows = await db_pool.fetch("SELECT id FROM event_outbox")
    assert len(rows) == 1
    expected = uuid.uuid5(outbox._EVENT_NAMESPACE, f"docflow.document.created.v1|{doc}")
    assert rows[0]["id"] == expected


async def test_enqueue_without_dedup_key_is_random(
    db_pool: asyncpg.Pool, test_workspace: dict, emit: None
) -> None:
    # Sans dedup_key (ex. moved/retyped, répétables) : id aléatoire → deux
    # enqueues du même changement produisent deux events distincts (pas de perte).
    wk = test_workspace["workspace_technical_key"]

    async def _push() -> None:
        async with db_pool.acquire() as conn, conn.transaction():
            await outbox.enqueue(
                conn,
                event_code="docflow.document.moved.v1",
                workspace_wk=wk,
                business={"documentId": "x"},
            )

    await _push()
    await _push()
    assert len(await db_pool.fetch("SELECT id FROM event_outbox")) == 2


def test_envelope_flat_and_collision() -> None:
    import uuid

    env = outbox.build_envelope(
        uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "docflow.document.created.v1",
        __import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").UTC),
        "docflow-test",
        {"documentId": "d1", "title": "T"},
    )
    assert env["_eventCode"] == "docflow.document.created.v1"
    assert env["_source"] == "docflow-test"
    assert env["_specVersion"] == catalog.SPEC_VERSION
    # Champs métier à la racine (pas de wrapper data).
    assert env["documentId"] == "d1"
    assert env["title"] == "T"
    with pytest.raises(ValueError, match="collision"):
        outbox.build_envelope(
            uuid.UUID("00000000-0000-0000-0000-000000000001"),
            "docflow.document.created.v1",
            __import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").UTC),
            "docflow-test",
            {"_eventId": "pirate"},
        )


# ── Émission désactivée : aucun effet ─────────────────────────────────────────


async def test_disabled_no_row(db_pool: asyncpg.Pool, test_workspace: dict, make_block) -> None:
    await db_pool.execute("DELETE FROM event_outbox")
    outbox.configure(enabled=False, source="docflow")
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    block_id = await make_block(_WS, "epic", "epic-block")
    await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="A", functional_type_slug="epic", block_id=block_id)
    )
    assert await _events(db_pool) == []


# ── Émission activée : un event par mutation ──────────────────────────────────


async def test_created_via_service(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block, emit: None
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    block_id = await make_block(_WS, "epic", "epic-block")
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="A", functional_type_slug="epic", block_id=block_id)
    )
    events = await _events(db_pool)
    assert len(events) == 1
    code, env = events[0]
    assert code == "docflow.document.created.v1"
    assert env["documentId"] == str(doc.doc_technical_key)
    assert env["workspaceSlug"] == _WS
    assert env["blockSlug"] == "epic-block"
    assert env["functionalTypeSlug"] == "epic"
    assert env["parentId"] is None
    assert env["title"] == "A"


async def test_created_via_block_ops(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block, emit: None
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await make_block(_WS, "epic", "epic-block")
    await block_ops.create_document_in_block(
        db_pool,
        _WS,
        "epic-block",
        DocumentCreateInBlock(title="Via block", slug="via-block", functional_type_slug="epic"),
    )
    events = await _events(db_pool)
    assert [c for c, _ in events] == ["docflow.document.created.v1"]
    assert events[0][1]["blockSlug"] == "epic-block"


async def test_updated_emits_version(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block, emit: None
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    block_id = await make_block(_WS, "epic", "epic-block")
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="A", content="# v1", functional_type_slug="epic", block_id=block_id),
    )
    await doc_svc.update_document(
        db_pool,
        _WS,
        doc.doc_technical_key,
        DocumentUpdate(title="A2", expected_version=1),
    )
    events = await _events(db_pool)
    codes = [c for c, _ in events]
    assert codes == ["docflow.document.created.v1", "docflow.document.updated.v1"]
    _, upd = events[1]
    assert upd["version"] == 2
    assert upd["title"] == "A2"


async def test_moved_and_retyped(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block, emit: None
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="feature", label="Feature", parent_slug="epic")
    )
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="bug", label="Bug", parent_slug="epic")
    )
    block_id = await make_block(_WS, "epic", "epic-block")
    a1 = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="A1", functional_type_slug="epic", block_id=block_id)
    )
    a2 = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="A2", functional_type_slug="epic", block_id=block_id)
    )
    feat = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="F",
            functional_type_slug="feature",
            block_id=block_id,
            parent_id=a1.doc_technical_key,
        ),
    )
    await db_pool.execute("DELETE FROM event_outbox")  # ne garder que la suite

    # Reparentage A1 → A2 (feature reste un fils valide d'epic).
    await doc_svc.update_document(
        db_pool, _WS, feat.doc_technical_key, DocumentUpdate(parent_id=a2.doc_technical_key)
    )
    # Retypage feature → bug (les deux sont fils d'epic, position inchangée).
    await doc_svc.update_document(
        db_pool, _WS, feat.doc_technical_key, DocumentUpdate(functional_type_slug="bug")
    )
    events = await _events(db_pool)
    codes = [c for c, _ in events]
    assert "docflow.document.moved.v1" in codes
    assert "docflow.document.retyped.v1" in codes
    moved = next(e for c, e in events if c == "docflow.document.moved.v1")
    assert moved["parentId"] == str(a2.doc_technical_key)
    retyped = next(e for c, e in events if c == "docflow.document.retyped.v1")
    assert retyped["functionalTypeSlug"] == "bug"


async def test_deleted_emits_before_cascade(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block, emit: None
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    block_id = await make_block(_WS, "epic", "epic-block")
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="A", functional_type_slug="epic", block_id=block_id)
    )
    await db_pool.execute("DELETE FROM event_outbox")
    await doc_svc.delete_document(db_pool, _WS, doc.doc_technical_key)
    events = await _events(db_pool)
    assert [c for c, _ in events] == ["docflow.document.deleted.v1"]
    _, env = events[0]
    assert env["documentId"] == str(doc.doc_technical_key)
    assert env["blockSlug"] == "epic-block"
    assert env["functionalTypeSlug"] == "epic"


async def test_property_changed(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block, emit: None
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await prop_svc.create_def(
        db_pool, _WS, "epic", PropertiesDefCreate(slug="prio", label="Prio", type="text")
    )
    block_id = await make_block(_WS, "epic", "epic-block")
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="A", functional_type_slug="epic", block_id=block_id)
    )
    await db_pool.execute("DELETE FROM event_outbox")
    await doc_svc.set_property_value(
        db_pool,
        _WS,
        doc.doc_technical_key,
        "prio",
        PropertyValueSet(value="high", expected_version=0),
    )
    events = await _events(db_pool)
    assert [c for c, _ in events] == ["docflow.document.propertyChanged.v1"]
    _, env = events[0]
    assert env["propSlug"] == "prio"
    assert env["propType"] == "text"
    assert env["value"] == "high"
    assert env["allowedValueSlug"] is None

"""Feature 4 — Référencement ``dataset://id`` dans le document.

Miroir du volet « références » de ``test_artifacts.py`` : parser pur, sync des
références au save (création de ligne ``dataset_reference``, purge refcount-0),
isolation workspace et purge différée des jamais-référencés.
"""

from __future__ import annotations

import uuid

import asyncpg

from docflow.datasets.parser import extract_dataset_ids

# ── Parser (unitaire, sans DB) ────────────────────────────────────────────────


def test_extract_single_dataset_id() -> None:
    did = "550e8400-e29b-41d4-a716-446655440000"
    md = f"Voir le tableau dataset://{did} ci-dessus."
    assert extract_dataset_ids(md) == [did]


def test_extract_multiple_and_dedup_preserves_order() -> None:
    d1 = "00000000-0000-0000-0000-000000000001"
    d2 = "00000000-0000-0000-0000-000000000002"
    md = f"dataset://{d1} puis dataset://{d2} et encore dataset://{d1}"
    assert extract_dataset_ids(md) == [d1, d2]


def test_extract_ignores_malformed_uuid() -> None:
    md = "dataset://not-a-uuid et dataset://1234"
    assert extract_dataset_ids(md) == []


def test_extract_ignores_other_schemes() -> None:
    md = "docflow://doc/550e8400-e29b-41d4-a716-446655440000 https://x/dataset"
    assert extract_dataset_ids(md) == []


def test_extract_empty_and_none() -> None:
    assert extract_dataset_ids("") == []
    assert extract_dataset_ids(None) == []


# ── Helpers DB ────────────────────────────────────────────────────────────────


async def _create_doc(
    db_pool: asyncpg.Pool, ws: dict[str, object], block: dict[str, object], title: str
) -> uuid.UUID:
    row = await db_pool.fetchrow(
        "INSERT INTO document "
        "(title, functional_type_ref, workspace_technical_key, data_block_ref) "
        "VALUES ($1, $2, $3, $4) RETURNING doc_technical_key",
        title,
        block["type_id"],
        ws["workspace_technical_key"],
        block["id"],
    )
    assert row is not None
    doc_id: uuid.UUID = row["doc_technical_key"]
    await db_pool.execute(
        "INSERT INTO document_version (document_ref, version_number, title, content) "
        "VALUES ($1, 1, $2, NULL)",
        doc_id,
        title,
    )
    return doc_id


async def _make_dataset(pool: asyncpg.Pool, wk: uuid.UUID, slug: str) -> uuid.UUID:
    return await pool.fetchval(
        "INSERT INTO dataset (workspace_technical_key, slug, label) "
        "VALUES ($1, $2, $3) RETURNING id",
        wk,
        slug,
        slug,
    )


def _token(dataset_id: uuid.UUID) -> str:
    return f"dataset://{dataset_id}"


# ── Sync + refcount 0 → suppression ──────────────────────────────────────────


async def test_refresh_creates_reference_then_removes_and_purges(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    from docflow.datasets import references

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    ds = await _make_dataset(db_pool, wk, "ventes")
    doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc dataset")

    async with db_pool.acquire() as conn:
        await references.refresh_dataset_references(conn, doc_id, wk, _token(ds))
    count = await db_pool.fetchval(
        "SELECT count(*) FROM dataset_reference WHERE document_ref = $1", doc_id
    )
    assert count == 1

    async with db_pool.acquire() as conn:
        await references.refresh_dataset_references(conn, doc_id, wk, "plus de tableau")
    gone = await db_pool.fetchval("SELECT 1 FROM dataset WHERE id = $1", ds)
    assert gone is None  # dernière référence retirée → refcount 0 → purge


async def test_refresh_keeps_dataset_referenced_elsewhere(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    from docflow.datasets import references

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    ds = await _make_dataset(db_pool, wk, "partage")
    doc_a = await _create_doc(db_pool, test_workspace, test_block, "Doc A")
    doc_b = await _create_doc(db_pool, test_workspace, test_block, "Doc B")

    async with db_pool.acquire() as conn:
        await references.refresh_dataset_references(conn, doc_a, wk, _token(ds))
        await references.refresh_dataset_references(conn, doc_b, wk, _token(ds))
        # A retire sa référence : le dataset reste (utilisé par B)
        await references.refresh_dataset_references(conn, doc_a, wk, "rien")
    still = await db_pool.fetchval("SELECT 1 FROM dataset WHERE id = $1", ds)
    assert still == 1
    # Retirer aussi de B → refcount 0 → purge
    async with db_pool.acquire() as conn:
        await references.refresh_dataset_references(conn, doc_b, wk, "rien")
    gone = await db_pool.fetchval("SELECT 1 FROM dataset WHERE id = $1", ds)
    assert gone is None


async def test_refresh_ignores_unknown_and_foreign_datasets(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Référence vers un dataset inexistant ou d'un autre workspace : ignorée
    (aucune ligne, le save ne casse pas)."""
    from docflow.datasets import references

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    other = await db_pool.fetchrow(
        "INSERT INTO workspace (slug, label) VALUES ('ds-ws-for', 'For') "
        "RETURNING workspace_technical_key"
    )
    assert other is not None
    try:
        foreign_wk: uuid.UUID = other["workspace_technical_key"]
        foreign_ds = await _make_dataset(db_pool, foreign_wk, "etranger")
        doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc étranger")
        content = f"dataset://{uuid.uuid4()} et dataset://{foreign_ds}"
        async with db_pool.acquire() as conn:
            await references.refresh_dataset_references(conn, doc_id, wk, content)
        count = await db_pool.fetchval(
            "SELECT count(*) FROM dataset_reference WHERE document_ref = $1", doc_id
        )
        assert count == 0
        # Le dataset étranger n'est pas touché
        assert await db_pool.fetchval("SELECT 1 FROM dataset WHERE id = $1", foreign_ds) == 1
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = 'ds-ws-for'")


# ── Purge différée des jamais-référencés ─────────────────────────────────────


async def test_purge_stale_only_old_unreferenced(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    from docflow.datasets import references

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    stale = await _make_dataset(db_pool, wk, "stale")
    fresh = await _make_dataset(db_pool, wk, "fresh")
    referenced = await _make_dataset(db_pool, wk, "referenced")
    doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc ref")
    async with db_pool.acquire() as conn:
        await references.refresh_dataset_references(conn, doc_id, wk, _token(referenced))
    # Vieillir artificiellement stale + referenced
    await db_pool.execute(
        "UPDATE dataset SET created_at = now() - interval '48 hours' WHERE id = ANY($1::uuid[])",
        [stale, referenced],
    )
    purged = await references.purge_stale_datasets(db_pool, older_than_hours=24)
    assert purged == 1
    assert await db_pool.fetchval("SELECT 1 FROM dataset WHERE id = $1", stale) is None
    assert await db_pool.fetchval("SELECT 1 FROM dataset WHERE id = $1", fresh) == 1
    assert await db_pool.fetchval("SELECT 1 FROM dataset WHERE id = $1", referenced) == 1


async def test_never_referenced_dataset_survives_save(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Un dataset créé puis jamais référencé n'est PAS supprimé par un save qui
    ne le mentionne pas (pas d'ancienne référence à retirer)."""
    from docflow.datasets import references

    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    ds = await _make_dataset(db_pool, wk, "orphelin")
    doc_id = await _create_doc(db_pool, test_workspace, test_block, "Doc sans ref")
    async with db_pool.acquire() as conn:
        await references.refresh_dataset_references(conn, doc_id, wk, "aucun tableau ici")
    assert await db_pool.fetchval("SELECT 1 FROM dataset WHERE id = $1", ds) == 1

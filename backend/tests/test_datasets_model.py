"""Feature 1 — Modèle SQL des datasets tabulaires.

Deux volets :
  - contraintes SQL (cascade, UNIQUE, CHECK, PK composite) via SQL brut ;
  - coercion PURE des valeurs de cellule selon le type de colonne.
"""

from __future__ import annotations

import datetime
import uuid

import asyncpg
import pytest

from docflow.datasets.coercion import coerce_cell


# ---------------------------------------------------------------------------
# Helpers de fabrication (SQL brut, paramétré)
# ---------------------------------------------------------------------------
async def _make_dataset(pool: asyncpg.Pool, wk: uuid.UUID, slug: str) -> uuid.UUID:
    return await pool.fetchval(
        "INSERT INTO dataset (workspace_technical_key, slug, label) "
        "VALUES ($1, $2, $3) RETURNING id",
        wk,
        slug,
        slug,
    )


async def _make_column(
    pool: asyncpg.Pool, dataset_ref: uuid.UUID, slug: str, col_type: str
) -> uuid.UUID:
    return await pool.fetchval(
        "INSERT INTO dataset_column (dataset_ref, slug, label, type) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        dataset_ref,
        slug,
        slug,
        col_type,
    )


async def _make_row(pool: asyncpg.Pool, dataset_ref: uuid.UUID) -> uuid.UUID:
    return await pool.fetchval(
        "INSERT INTO dataset_row (dataset_ref) VALUES ($1) RETURNING id",
        dataset_ref,
    )


# ---------------------------------------------------------------------------
# Contraintes SQL
# ---------------------------------------------------------------------------
async def test_delete_dataset_cascades(
    db_pool: asyncpg.Pool,
    test_workspace: dict[str, object],
    test_block: dict[str, object],
) -> None:
    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    block_id: uuid.UUID = test_block["id"]  # type: ignore[assignment]
    dataset_id = await _make_dataset(db_pool, wk, "ds-cascade")
    col_id = await _make_column(db_pool, dataset_id, "col-a", "text")
    row_id = await _make_row(db_pool, dataset_id)
    await db_pool.execute(
        "INSERT INTO dataset_cell (row_ref, column_ref, value) VALUES ($1, $2, $3)",
        row_id,
        col_id,
        "hello",
    )
    doc_id = await db_pool.fetchval(
        "INSERT INTO document (title, workspace_technical_key, data_block_ref) "
        "VALUES ($1, $2, $3) RETURNING doc_technical_key",
        "doc-ref",
        wk,
        block_id,
    )
    await db_pool.execute(
        "INSERT INTO dataset_reference (dataset_ref, document_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3)",
        dataset_id,
        doc_id,
        wk,
    )

    await db_pool.execute("DELETE FROM dataset WHERE id = $1", dataset_id)

    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM dataset_column WHERE dataset_ref = $1", dataset_id
        )
        == 0
    )
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM dataset_row WHERE dataset_ref = $1", dataset_id
        )
        == 0
    )
    assert (
        await db_pool.fetchval("SELECT count(*) FROM dataset_cell WHERE row_ref = $1", row_id) == 0
    )
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM dataset_reference WHERE dataset_ref = $1", dataset_id
        )
        == 0
    )
    # Le document lui-même n'est pas supprimé par la cascade du dataset.
    assert (
        await db_pool.fetchval("SELECT count(*) FROM document WHERE doc_technical_key = $1", doc_id)
        == 1
    )


async def test_column_slug_unique_per_dataset(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    dataset_id = await _make_dataset(db_pool, wk, "ds-uniq")
    await _make_column(db_pool, dataset_id, "dup", "text")
    with pytest.raises(asyncpg.UniqueViolationError):
        await _make_column(db_pool, dataset_id, "dup", "int")


async def test_column_type_check(db_pool: asyncpg.Pool, test_workspace: dict[str, object]) -> None:
    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    dataset_id = await _make_dataset(db_pool, wk, "ds-check")
    with pytest.raises(asyncpg.CheckViolationError):
        await _make_column(db_pool, dataset_id, "bad", "timestamp")


async def test_cell_pk_unique_row_column(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    wk: uuid.UUID = test_workspace["workspace_technical_key"]  # type: ignore[assignment]
    dataset_id = await _make_dataset(db_pool, wk, "ds-pk")
    col_id = await _make_column(db_pool, dataset_id, "col", "text")
    row_id = await _make_row(db_pool, dataset_id)
    await db_pool.execute(
        "INSERT INTO dataset_cell (row_ref, column_ref, value) VALUES ($1, $2, $3)",
        row_id,
        col_id,
        "a",
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await db_pool.execute(
            "INSERT INTO dataset_cell (row_ref, column_ref, value) VALUES ($1, $2, $3)",
            row_id,
            col_id,
            "b",
        )


# ---------------------------------------------------------------------------
# coerce_cell — cellule vide
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw", [None, "", "   "])
def test_coerce_empty_gives_all_none(raw: str | None) -> None:
    assert coerce_cell("int", raw) == {
        "value": None,
        "num_value": None,
        "date_value": None,
        "bool_value": None,
    }


# ---------------------------------------------------------------------------
# coerce_cell — valides
# ---------------------------------------------------------------------------
def test_coerce_text() -> None:
    assert coerce_cell("text", "salut") == {
        "value": "salut",
        "num_value": None,
        "date_value": None,
        "bool_value": None,
    }


def test_coerce_int() -> None:
    out = coerce_cell("int", "42")
    assert out == {
        "value": "42",
        "num_value": 42,
        "date_value": None,
        "bool_value": None,
    }


def test_coerce_float() -> None:
    out = coerce_cell("float", "3.14")
    assert out["value"] == "3.14"
    assert out["num_value"] == pytest.approx(3.14)
    assert out["date_value"] is None
    assert out["bool_value"] is None


def test_coerce_date() -> None:
    out = coerce_cell("date", "2026-07-16")
    assert out == {
        "value": "2026-07-16",
        "num_value": None,
        "date_value": datetime.date(2026, 7, 16),
        "bool_value": None,
    }


def test_coerce_url() -> None:
    out = coerce_cell("url", "https://doc.yoops.org/x")
    assert out["value"] == "https://doc.yoops.org/x"
    assert out["num_value"] is None
    assert out["date_value"] is None
    assert out["bool_value"] is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("false", False),
        ("1", True),
        ("0", False),
        ("VRAI", True),
        ("Faux", False),
    ],
)
def test_coerce_bool_valid(raw: str, expected: bool) -> None:
    out = coerce_cell("bool", raw)
    assert out["bool_value"] is expected
    assert out["value"] == raw
    assert out["num_value"] is None
    assert out["date_value"] is None


# ---------------------------------------------------------------------------
# coerce_cell — invalides
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("col_type", "raw"),
    [
        ("int", "abc"),
        ("float", "abc"),
        ("date", "2026-13-99"),
        ("date", "hier"),
        ("bool", "peut-être"),
        ("url", "ftp://x"),
        ("url", "doc.yoops.org"),
    ],
)
def test_coerce_invalid_raises(col_type: str, raw: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        coerce_cell(col_type, raw)  # type: ignore[arg-type]
    # message clair : mentionne la valeur et le type
    msg = str(excinfo.value)
    assert raw in msg
    assert col_type in msg

"""Tests Feature 2 — service + tools MCP ``dataset_*``.

Cycle CRUD, retypage atomique, requêtage par ombre typée, garde d'accès
workspace via ``_call_tool``, et erreurs propres (404/409/422).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.datasets import service
from docflow.datasets.query import query_dataset
from docflow.mcp.server import _call_tool, configure
from docflow.mcp.session import McpSession, reset_current_session, set_current_session
from docflow.schemas.auth import AuthUser


def _json(result: list) -> dict:
    return json.loads((result.content if hasattr(result, "content") else result)[0].text)


def _admin_user(uid: uuid.UUID) -> AuthUser:
    return AuthUser(
        id=uid,
        email="ds-admin@test.local",
        label="DS Admin",
        is_admin=True,
        validated=True,
        disabled=False,
    )


@pytest.fixture()
async def ws(db_pool: asyncpg.Pool) -> AsyncIterator[dict[str, object]]:
    """Workspace + session superadmin liée au contexte MCP."""
    configure(db_pool)
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "ds-ws")
    wk = await db_pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) RETURNING workspace_technical_key",
        "ds-ws",
        "DS WS",
    )
    uid = await db_pool.fetchval(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, true) "
        "ON CONFLICT (email) DO UPDATE SET label = EXCLUDED.label RETURNING id",
        "ds-admin@test.local",
        "DS Admin",
    )
    token = set_current_session(McpSession(user=_admin_user(uid)))
    try:
        yield {"wk": wk, "ws_slug": "ds-ws", "uid": uid}
    finally:
        reset_current_session(token)
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "ds-ws")
        await db_pool.execute("DELETE FROM app_user WHERE email = 'ds-admin@test.local'")


async def _new_dataset(pool: asyncpg.Pool, ws_slug: str, slug: str = "sprint") -> uuid.UUID:
    created = _json(
        await _call_tool(
            "create_dataset", {"workspace_slug": ws_slug, "slug": slug, "label": "Sprint"}
        )
    )
    return uuid.UUID(created["id"])


# ---------------------------------------------------------------------------
# Cycle CRUD complet
# ---------------------------------------------------------------------------


async def test_full_cycle(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    ds_id = await _new_dataset(db_pool, ws_slug)

    for col in (
        {"slug": "titre", "label": "Titre", "type": "text"},
        {"slug": "points", "label": "Points", "type": "int"},
        {"slug": "echeance", "label": "Échéance", "type": "date"},
    ):
        res = _json(
            await _call_tool(
                "add_dataset_column",
                {
                    "workspace_slug": ws_slug,
                    "dataset_id": str(ds_id),
                    **col,
                },
            )
        )
        assert res["slug"] == col["slug"]

    row = _json(
        await _call_tool(
            "add_dataset_row",
            {
                "workspace_slug": ws_slug,
                "dataset_id": str(ds_id),
                "cells": {"titre": "A", "points": "5", "echeance": "2026-01-15"},
            },
        )
    )
    row_id = row["row_id"]

    ds = _json(
        await _call_tool(
            "get_dataset",
            {
                "workspace_slug": ws_slug,
                "dataset_id": str(ds_id),
            },
        )
    )
    assert [c["slug"] for c in ds["columns"]] == ["titre", "points", "echeance"]
    assert len(ds["rows"]) == 1
    assert ds["rows"][0]["cells"] == {"titre": "A", "points": "5", "echeance": "2026-01-15"}

    # list_datasets counts
    listed = _json(await _call_tool("list_datasets", {"workspace_slug": ws_slug}))
    entry = next(d for d in listed if d["id"] == str(ds_id))
    assert entry["column_count"] == 3 and entry["row_count"] == 1

    # update_row : upsert d'une cellule
    _json(
        await _call_tool(
            "update_dataset_row",
            {
                "workspace_slug": ws_slug,
                "dataset_id": str(ds_id),
                "row_id": row_id,
                "cells": {"points": "8"},
            },
        )
    )
    ds = _json(
        await _call_tool(
            "get_dataset",
            {
                "workspace_slug": ws_slug,
                "dataset_id": str(ds_id),
            },
        )
    )
    assert ds["rows"][0]["cells"]["points"] == "8"
    assert ds["rows"][0]["cells"]["titre"] == "A"

    # delete_row / delete_column
    _json(
        await _call_tool(
            "delete_dataset_row",
            {
                "workspace_slug": ws_slug,
                "dataset_id": str(ds_id),
                "row_id": row_id,
            },
        )
    )
    _json(
        await _call_tool(
            "delete_dataset_column",
            {
                "workspace_slug": ws_slug,
                "dataset_id": str(ds_id),
                "column_slug": "echeance",
            },
        )
    )
    ds = _json(
        await _call_tool(
            "get_dataset",
            {
                "workspace_slug": ws_slug,
                "dataset_id": str(ds_id),
            },
        )
    )
    assert ds["rows"] == []
    assert [c["slug"] for c in ds["columns"]] == ["titre", "points"]


async def test_add_row_unknown_column(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    ds_id = await _new_dataset(db_pool, ws_slug)
    res = _json(
        await _call_tool(
            "add_dataset_row",
            {
                "workspace_slug": ws_slug,
                "dataset_id": str(ds_id),
                "cells": {"nope": "x"},
            },
        )
    )
    assert "error" in res and "inconnue" in res["error"]


# ---------------------------------------------------------------------------
# Retypage atomique
# ---------------------------------------------------------------------------


async def test_retype_text_to_int_ok(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    ds_id = await _new_dataset(db_pool, ws_slug)
    await service.add_column(db_pool, ws_slug, ds_id, "n", "N", "text")
    await service.add_row(db_pool, ws_slug, ds_id, {"n": "10"})
    await service.add_row(db_pool, ws_slug, ds_id, {"n": "20"})

    updated = await service.update_column(db_pool, ws_slug, ds_id, "n", type="int")
    assert updated["type"] == "int"

    # les ombres num_value sont désormais renseignées → requêtable numériquement
    res = await query_dataset(db_pool, ws_slug, ds_id, [{"column": "n", "op": "gt", "value": 15}])
    assert res["total"] == 1
    assert res["rows"][0]["cells"]["n"] == "20"


async def test_retype_rejected_atomic(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    ds_id = await _new_dataset(db_pool, ws_slug)
    await service.add_column(db_pool, ws_slug, ds_id, "n", "N", "text")
    await service.add_row(db_pool, ws_slug, ds_id, {"n": "10"})
    await service.add_row(db_pool, ws_slug, ds_id, {"n": "abc"})

    with pytest.raises(HTTPException) as exc:
        await service.update_column(db_pool, ws_slug, ds_id, "n", type="int")
    assert exc.value.status_code == 422
    assert "abc" in str(exc.value.detail)

    # aucune modification : la colonne reste en text
    ds = await service.get_dataset(db_pool, ws_slug, ds_id)
    col = next(c for c in ds["columns"] if c["slug"] == "n")  # type: ignore[index]
    assert col["type"] == "text"


# ---------------------------------------------------------------------------
# Requêtage
# ---------------------------------------------------------------------------


@pytest.fixture()
async def dataset_query(db_pool: asyncpg.Pool, ws: dict[str, object]) -> dict[str, object]:
    ws_slug = str(ws["ws_slug"])
    ds_id = await _new_dataset(db_pool, ws_slug, "q")
    await service.add_column(db_pool, ws_slug, ds_id, "titre", "Titre", "text")
    await service.add_column(db_pool, ws_slug, ds_id, "score", "Score", "int")
    await service.add_column(db_pool, ws_slug, ds_id, "jour", "Jour", "date")
    data = [
        {"titre": "alpha", "score": "50", "jour": "2026-01-01"},
        {"titre": "beta", "score": "150", "jour": "2026-03-01"},
        {"titre": "gamma alpha", "score": "250", "jour": "2026-05-01"},
    ]
    for cells in data:
        await service.add_row(db_pool, ws_slug, ds_id, cells)
    return {"ws_slug": ws_slug, "ds_id": ds_id}


async def test_query_numeric_filter(
    db_pool: asyncpg.Pool, dataset_query: dict[str, object]
) -> None:
    res = await query_dataset(
        db_pool,
        str(dataset_query["ws_slug"]),
        dataset_query["ds_id"],  # type: ignore[arg-type]
        [{"column": "score", "op": "gt", "value": 100}],
    )
    assert res["total"] == 2
    assert {r["cells"]["titre"] for r in res["rows"]} == {"beta", "gamma alpha"}


async def test_query_contains_filter(
    db_pool: asyncpg.Pool, dataset_query: dict[str, object]
) -> None:
    res = await query_dataset(
        db_pool,
        str(dataset_query["ws_slug"]),
        dataset_query["ds_id"],  # type: ignore[arg-type]
        [{"column": "titre", "op": "contains", "value": "alpha"}],
    )
    assert res["total"] == 2


async def test_query_date_and_combined(
    db_pool: asyncpg.Pool, dataset_query: dict[str, object]
) -> None:
    res = await query_dataset(
        db_pool,
        str(dataset_query["ws_slug"]),
        dataset_query["ds_id"],  # type: ignore[arg-type]
        [
            {"column": "jour", "op": "gte", "value": "2026-03-01"},
            {"column": "score", "op": "lt", "value": 250},
        ],
    )
    assert res["total"] == 1
    assert res["rows"][0]["cells"]["titre"] == "beta"


async def test_query_sort_and_pagination(
    db_pool: asyncpg.Pool, dataset_query: dict[str, object]
) -> None:
    res = await query_dataset(
        db_pool,
        str(dataset_query["ws_slug"]),
        dataset_query["ds_id"],  # type: ignore[arg-type]
        [],
        {"column": "score", "dir": "desc"},
        page=1,
        page_size=2,
    )
    assert res["total"] == 3
    assert res["page_size"] == 2
    assert [r["cells"]["score"] for r in res["rows"]] == ["250", "150"]

    page2 = await query_dataset(
        db_pool,
        str(dataset_query["ws_slug"]),
        dataset_query["ds_id"],  # type: ignore[arg-type]
        [],
        {"column": "score", "dir": "desc"},
        page=2,
        page_size=2,
    )
    assert [r["cells"]["score"] for r in page2["rows"]] == ["50"]


async def test_query_via_call_tool(db_pool: asyncpg.Pool, dataset_query: dict[str, object]) -> None:
    res = _json(
        await _call_tool(
            "query_dataset",
            {
                "workspace_slug": str(dataset_query["ws_slug"]),
                "dataset_id": str(dataset_query["ds_id"]),
                "filters": [{"column": "score", "op": "gte", "value": 150}],
                "sort": {"column": "score", "dir": "asc"},
            },
        )
    )
    assert res["total"] == 2
    assert [r["cells"]["score"] for r in res["rows"]] == ["150", "250"]


# ---------------------------------------------------------------------------
# Erreurs : 404 / 409
# ---------------------------------------------------------------------------


async def test_unknown_workspace(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    with pytest.raises(HTTPException) as exc:
        await service.create_dataset(db_pool, "no-such-ws", "x", "X", None)
    assert exc.value.status_code == 404


async def test_unknown_dataset(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    with pytest.raises(HTTPException) as exc:
        await service.get_dataset(db_pool, str(ws["ws_slug"]), uuid.uuid4())
    assert exc.value.status_code == 404


async def test_duplicate_dataset_slug(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    await service.create_dataset(db_pool, ws_slug, "dup", "Dup", None)
    with pytest.raises(HTTPException) as exc:
        await service.create_dataset(db_pool, ws_slug, "dup", "Dup 2", None)
    assert exc.value.status_code == 409


async def test_duplicate_column_slug(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    ds_id = await _new_dataset(db_pool, ws_slug, "dupcol")
    await service.add_column(db_pool, ws_slug, ds_id, "c", "C", "text")
    with pytest.raises(HTTPException) as exc:
        await service.add_column(db_pool, ws_slug, ds_id, "c", "C2", "int")
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Garde d'accès workspace via _call_tool
# ---------------------------------------------------------------------------


async def test_access_denied_for_non_member(db_pool: asyncpg.Pool, ws: dict[str, object]) -> None:
    ws_slug = str(ws["ws_slug"])
    ds_id = await _new_dataset(db_pool, ws_slug)

    # Bascule sur un utilisateur non-admin sans accès au workspace (owner NULL).
    outsider_id = await db_pool.fetchval(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, true) "
        "ON CONFLICT (email) DO UPDATE SET label = EXCLUDED.label RETURNING id",
        "ds-outsider@test.local",
        "Outsider",
    )
    outsider = AuthUser(
        id=outsider_id,
        email="ds-outsider@test.local",
        label="Outsider",
        is_admin=False,
        validated=True,
        disabled=False,
    )
    token = set_current_session(McpSession(user=outsider))
    try:
        res = _json(
            await _call_tool(
                "get_dataset",
                {
                    "workspace_slug": ws_slug,
                    "dataset_id": str(ds_id),
                },
            )
        )
        assert "error" in res and "accès refusé" in res["error"]
        res_w = _json(
            await _call_tool(
                "add_dataset_row",
                {
                    "workspace_slug": ws_slug,
                    "dataset_id": str(ds_id),
                    "cells": {},
                },
            )
        )
        assert "error" in res_w and "accès refusé" in res_w["error"]
    finally:
        reset_current_session(token)
        await db_pool.execute("DELETE FROM app_user WHERE email = 'ds-outsider@test.local'")

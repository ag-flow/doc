"""Base CSS des maquettes (mockup-base) : marqueurs, set, apply, propagate, drift."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.artifacts import mockup_base as mb
from docflow.artifacts import service as art_svc

_WS = "test-ws"
_MAX = 1_000_000


# ── Marqueurs (unitaire, sans DB) ─────────────────────────────────────────────


def test_build_and_find_block_roundtrip() -> None:
    bid = uuid.uuid4()
    block = mb.build_block(bid, 3, ":root{--c:#111}")
    html = f"<html><head>{block}</head><body>x</body></html>"
    found = mb.find_block(html, bid)
    assert found is not None
    assert found[0] == block
    assert found[1] == 3


def test_find_block_absent_and_other_base() -> None:
    bid, other = uuid.uuid4(), uuid.uuid4()
    html = f"<head>{mb.build_block(other, 1, 'a{}')}</head>"
    assert mb.find_block(html, bid) is None


def test_find_block_multiple_is_corruption() -> None:
    bid = uuid.uuid4()
    dup = mb.build_block(bid, 1, "a{}") + mb.build_block(bid, 2, "b{}")
    with pytest.raises(HTTPException):
        mb.find_block(dup, bid)


def test_insert_block_before_head() -> None:
    out = mb._insert_block(
        "<html><head><title>t</title></head><body></body></html>", "<style></style>"
    )
    assert out.index("<style></style>") < out.index("</head>")


def test_insert_block_no_head_prepends() -> None:
    out = mb._insert_block("just text", "<style>x</style>")
    assert out.startswith("<style>x</style>")


# ── Service (DB) ──────────────────────────────────────────────────────────────


async def _new_maquette(db_pool: asyncpg.Pool, html: str) -> uuid.UUID:
    created = await art_svc.create_artifact(
        db_pool,
        _WS,
        filename=f"m-{uuid.uuid4().hex}.html",
        data=html.encode(),
        created_by=None,
        max_bytes=_MAX,
        mutable=True,
    )
    return created.id


async def test_set_create_then_update(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    created = await mb.set_mockup_base(
        db_pool, _WS, css="a{color:red}", updated_by=None, max_bytes=_MAX
    )
    assert created["revision"] == 1 and created["created"] is True
    base_id = created["base_id"]
    updated = await mb.set_mockup_base(
        db_pool,
        _WS,
        css="a{color:blue}",
        updated_by=None,
        max_bytes=_MAX,
        base_id=base_id,
        if_revision=1,
    )
    assert updated["revision"] == 2 and updated["created"] is False
    got = await mb.get_mockup_base(db_pool, _WS, base_id)
    assert got["css"] == "a{color:blue}" and got["revision"] == 2


async def test_apply_inserts_then_patches(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    base = await mb.set_mockup_base(
        db_pool, _WS, css=":root{--x:1}", updated_by=None, max_bytes=_MAX
    )
    base_id = base["base_id"]
    maq = await _new_maquette(db_pool, "<html><head></head><body>hi</body></html>")

    # 1er apply : insertion.
    r1 = await mb.apply_mockup_base(
        db_pool, _WS, maquette_id=maq, base_id=base_id, updated_by=None, max_bytes=_MAX
    )
    assert r1["changed"] is True and r1["base_rev"] == 1
    drift = await mb.mockup_base_drift(db_pool, _WS, base_id)
    assert drift["total"] == 1 and drift["stale"] == 0

    # bump base → apply de nouveau : remplacement par patch (ancre unique).
    await mb.set_mockup_base(
        db_pool,
        _WS,
        css=":root{--x:2}",
        updated_by=None,
        max_bytes=_MAX,
        base_id=base_id,
        if_revision=1,
    )
    r2 = await mb.apply_mockup_base(
        db_pool, _WS, maquette_id=maq, base_id=base_id, updated_by=None, max_bytes=_MAX
    )
    assert r2["changed"] is True and r2["base_rev"] == 2
    # un seul bloc, à jour.
    drift2 = await mb.mockup_base_drift(db_pool, _WS, base_id)
    assert drift2["total"] == 1 and drift2["stale"] == 0
    assert drift2["maquettes"][0]["embedded_rev"] == 2


async def test_apply_idempotent_when_up_to_date(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    base = await mb.set_mockup_base(db_pool, _WS, css="a{}", updated_by=None, max_bytes=_MAX)
    maq = await _new_maquette(db_pool, "<head></head>")
    await mb.apply_mockup_base(
        db_pool, _WS, maquette_id=maq, base_id=base["base_id"], updated_by=None, max_bytes=_MAX
    )
    again = await mb.apply_mockup_base(
        db_pool, _WS, maquette_id=maq, base_id=base["base_id"], updated_by=None, max_bytes=_MAX
    )
    assert again["changed"] is False  # rien à réécrire


async def test_propagate_updates_stale_skips_current(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    base = await mb.set_mockup_base(
        db_pool, _WS, css="a{color:red}", updated_by=None, max_bytes=_MAX
    )
    base_id = base["base_id"]
    m1 = await _new_maquette(db_pool, "<head></head><body>1</body>")
    m2 = await _new_maquette(db_pool, "<head></head><body>2</body>")
    await mb.apply_mockup_base(
        db_pool, _WS, maquette_id=m1, base_id=base_id, updated_by=None, max_bytes=_MAX
    )
    await mb.apply_mockup_base(
        db_pool, _WS, maquette_id=m2, base_id=base_id, updated_by=None, max_bytes=_MAX
    )

    # bump base ; m1/m2 sont maintenant en retard (rev1 vs rev2).
    await mb.set_mockup_base(
        db_pool,
        _WS,
        css="a{color:blue}",
        updated_by=None,
        max_bytes=_MAX,
        base_id=base_id,
        if_revision=1,
    )
    res = await mb.propagate_mockup_base(db_pool, _WS, base_id, updated_by=None, max_bytes=_MAX)
    assert len(res["updated"]) == 2 and res["current_rev"] == 2
    assert not res["failed"]

    # rejeu : tout est à jour → tout skippé, rien mis à jour.
    res2 = await mb.propagate_mockup_base(db_pool, _WS, base_id, updated_by=None, max_bytes=_MAX)
    assert not res2["updated"] and len(res2["skipped"]) == 2

    # le nouveau CSS est bien embarqué dans m1.
    content, _, _ = await art_svc.fetch_artifact_content(db_pool, _WS, m1)
    assert "a{color:blue}" in content.decode()
    drift = await mb.mockup_base_drift(db_pool, _WS, base_id)
    assert drift["stale"] == 0


async def test_scan_scopes_to_base_id(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """Une maquette d'une AUTRE base n'est pas ramassée par la propagation."""
    a = await mb.set_mockup_base(db_pool, _WS, css="x{}", updated_by=None, max_bytes=_MAX)
    b = await mb.set_mockup_base(db_pool, _WS, css="y{}", updated_by=None, max_bytes=_MAX)
    ma = await _new_maquette(db_pool, "<head></head>")
    mbq = await _new_maquette(db_pool, "<head></head>")
    await mb.apply_mockup_base(
        db_pool, _WS, maquette_id=ma, base_id=a["base_id"], updated_by=None, max_bytes=_MAX
    )
    await mb.apply_mockup_base(
        db_pool, _WS, maquette_id=mbq, base_id=b["base_id"], updated_by=None, max_bytes=_MAX
    )
    drift_a = await mb.mockup_base_drift(db_pool, _WS, a["base_id"])
    assert drift_a["total"] == 1 and drift_a["maquettes"][0]["maquette_id"] == ma


async def test_base_guard_rejects_non_css_target(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    maq = await _new_maquette(db_pool, "<head></head>")
    with pytest.raises(HTTPException):
        await mb.get_mockup_base(db_pool, _WS, maq)  # une maquette n'est pas une base

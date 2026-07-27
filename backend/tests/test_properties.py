from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.properties import service as prop_svc
from docflow.schemas.properties import (
    AllowedValueCreate,
    AllowedValueUpdate,
    PropertiesDefCreate,
    PropertiesDefUpdate,
)
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _make_type(pool: asyncpg.Pool, slug: str = "epic") -> str:
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug=slug, label=slug.capitalize()))
    return slug


async def _make_prop(
    pool: asyncpg.Pool, type_slug: str, prop_slug: str, prop_type: str = "text"
) -> str:
    await prop_svc.create_def(
        pool,
        _WS,
        type_slug,
        PropertiesDefCreate(slug=prop_slug, label=prop_slug.capitalize(), type=prop_type),  # type: ignore[arg-type]
    )
    return prop_slug


async def test_create_property_def(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    prop = await prop_svc.create_def(
        db_pool, _WS, "epic", PropertiesDefCreate(slug="title", label="Title", type="text")
    )
    assert prop.slug == "title"
    assert prop.type == "text"


async def test_property_slug_unique_per_type(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_def(
            db_pool,
            _WS,
            "epic",
            PropertiesDefCreate(slug="status", label="Status2", type="text"),
        )
    assert exc.value.status_code == 409


async def test_list_property_defs(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "title")
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    defs = await prop_svc.list_defs(db_pool, _WS, "epic")
    slugs = [d.slug for d in defs]
    assert "title" in slugs and "status" in slugs


async def test_update_property_label(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "title")
    updated = await prop_svc.update_def(
        db_pool, _WS, "epic", "title", PropertiesDefUpdate(label="Title (renamed)")
    )
    assert updated.label == "Title (renamed)"


async def test_delete_property_def(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "to-delete")
    await prop_svc.delete_def(db_pool, _WS, "epic", "to-delete")
    defs = await prop_svc.list_defs(db_pool, _WS, "epic")
    assert not any(d.slug == "to-delete" for d in defs)


async def test_allowed_value_only_on_restricted_list(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "title", "text")
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_allowed_value(
            db_pool, _WS, "epic", "title", AllowedValueCreate(slug="val", label="Val")
        )
    assert exc.value.status_code == 422


async def test_create_allowed_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    val = await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo", position=0)
    )
    assert val.slug == "todo"
    assert val.position == 0


async def test_allowed_value_slug_unique(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo")
    )
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_allowed_value(
            db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo2")
        )
    assert exc.value.status_code == 409


async def test_list_allowed_values_ordered(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="done", label="Done", position=2)
    )
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo", position=0)
    )
    values = await prop_svc.list_allowed_values(db_pool, _WS, "epic", "status")
    assert values[0].slug == "todo"
    assert values[1].slug == "done"


async def test_update_allowed_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo")
    )
    updated = await prop_svc.update_allowed_value(
        db_pool,
        _WS,
        "epic",
        "status",
        "todo",
        AllowedValueUpdate(label="À faire", color="#ff0000"),
    )
    assert updated.label == "À faire"
    assert updated.color == "#ff0000"


async def test_delete_allowed_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo")
    )
    await prop_svc.delete_allowed_value(db_pool, _WS, "epic", "status", "todo")
    values = await prop_svc.list_allowed_values(db_pool, _WS, "epic", "status")
    assert not any(v.slug == "todo" for v in values)


async def test_delete_allowed_value_used_reports_count(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD écran Types : le 409 annonce le nombre de documents concernés."""
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    av = await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="fait", label="Fait")
    )

    wk = test_workspace["workspace_technical_key"]
    async with db_pool.acquire() as conn:
        type_id = await conn.fetchval(
            "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='epic'", wk
        )
        prop_id = await conn.fetchval(
            "SELECT id FROM properties_defs WHERE functional_type_ref=$1 AND slug='status'",
            type_id,
        )
        block_id = await conn.fetchval(
            "INSERT INTO data_block (slug, label, functional_type_ref, "
            "workspace_technical_key) VALUES ('blk-409', 'B', $1, $2) RETURNING id",
            type_id,
            wk,
        )
        doc_id = await conn.fetchval(
            "INSERT INTO document (title, functional_type_ref, data_block_ref, "
            "workspace_technical_key) VALUES ('Doc', $1, $2, $3) RETURNING doc_technical_key",
            type_id,
            block_id,
            wk,
        )
        pv_id = await conn.fetchval(
            "INSERT INTO properties_values (document_ref, property_def_ref, "
            "workspace_technical_key, version) VALUES ($1, $2, $3, 1) RETURNING id",
            doc_id,
            prop_id,
            wk,
        )
        await conn.execute(
            "INSERT INTO properties_value_version (property_value_ref, version_number, "
            "allowed_value_ref) VALUES ($1, 1, $2)",
            pv_id,
            av.id,
        )

    with pytest.raises(HTTPException) as exc:
        await prop_svc.delete_allowed_value(db_pool, _WS, "epic", "status", "fait")
    assert exc.value.status_code == 409
    assert "1 document" in str(exc.value.detail)


async def test_types_rich_carries_documents_count(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _make_type(db_pool, "story")
    wk = test_workspace["workspace_technical_key"]
    async with db_pool.acquire() as conn:
        type_id = await conn.fetchval(
            "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='story'", wk
        )
        block_id = await conn.fetchval(
            "INSERT INTO data_block (slug, label, functional_type_ref, "
            "workspace_technical_key) VALUES ('blk-count', 'B', $1, $2) RETURNING id",
            type_id,
            wk,
        )
        await conn.execute(
            "INSERT INTO document (title, functional_type_ref, data_block_ref, "
            "workspace_technical_key) VALUES ('A', $1, $2, $3), ('B', $1, $2, $3)",
            type_id,
            block_id,
            wk,
        )
    rich = await type_svc.list_types_rich(db_pool, _WS)
    assert next(ty for ty in rich if ty.slug == "story").documents_count == 2

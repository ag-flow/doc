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
        db_pool, _WS, "epic", "status", "todo",
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

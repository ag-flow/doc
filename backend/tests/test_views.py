"""Tests spec 37 — MVIEW : vues sauvegardées."""
from __future__ import annotations

import uuid

import asyncpg
import pytest

from docflow.views import service as view_svc
from docflow.views.service import ViewCreate, ViewUpdate
from docflow.schemas.document import DocumentCreate
from docflow.documents import service as doc_svc


_CALLER = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def test_create_view_shared(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    ws = "test-ws"
    view = await view_svc.create_view(
        db_pool, ws, _CALLER,
        ViewCreate(slug="shared-view", label="Partagée", layout="table", shared=True),
    )
    assert view.slug == "shared-view"
    assert view.owner_ref is None  # shared


async def test_create_view_private(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    ws = "test-ws"
    view = await view_svc.create_view(
        db_pool, ws, _CALLER,
        ViewCreate(slug="private-view", label="Privée", layout="table", shared=False),
    )
    assert view.owner_ref == _CALLER


async def test_list_views_includes_shared_and_own(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    ws = "test-ws"
    other = uuid.UUID("00000000-0000-0000-0000-000000000002")
    await view_svc.create_view(
        db_pool, ws, _CALLER,
        ViewCreate(slug="shared-lv", label="Partagée", layout="table", shared=True),
    )
    await view_svc.create_view(
        db_pool, ws, _CALLER,
        ViewCreate(slug="mine-lv", label="La mienne", layout="table", shared=False),
    )
    await view_svc.create_view(
        db_pool, ws, other,
        ViewCreate(slug="others-lv", label="Autre user", layout="table", shared=False),
    )
    views = await view_svc.list_views(db_pool, ws, _CALLER)
    slugs = [v.slug for v in views]
    assert "shared-lv" in slugs
    assert "mine-lv" in slugs
    assert "others-lv" not in slugs


async def test_create_view_duplicate_slug_raises(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    from fastapi import HTTPException
    ws = "test-ws"
    await view_svc.create_view(
        db_pool, ws, _CALLER,
        ViewCreate(slug="dup-view", label="Dup", layout="table", shared=True),
    )
    with pytest.raises(HTTPException) as exc:
        await view_svc.create_view(
            db_pool, ws, _CALLER,
            ViewCreate(slug="dup-view", label="Dup2", layout="table", shared=True),
        )
    assert exc.value.status_code == 409


async def test_update_view_label(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    ws = "test-ws"
    await view_svc.create_view(
        db_pool, ws, _CALLER,
        ViewCreate(slug="upd-view", label="Initial", layout="table", shared=True),
    )
    updated = await view_svc.update_view(
        db_pool, ws, "upd-view", _CALLER, ViewUpdate(label="Mise à jour")
    )
    assert updated.label == "Mise à jour"


async def test_delete_view(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    from fastapi import HTTPException
    ws = "test-ws"
    await view_svc.create_view(
        db_pool, ws, _CALLER,
        ViewCreate(slug="del-view", label="À supprimer", layout="table", shared=True),
    )
    await view_svc.delete_view(db_pool, ws, "del-view", _CALLER)
    with pytest.raises(HTTPException) as exc:
        await view_svc.get_view(db_pool, ws, "del-view", _CALLER)
    assert exc.value.status_code == 404


async def test_resolve_view_empty_returns_all(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    ws = "test-ws"
    await doc_svc.create_document(
        db_pool, ws, DocumentCreate(title="Résolvable", parent_id=None)
    )
    await view_svc.create_view(
        db_pool, ws, _CALLER,
        ViewCreate(slug="resolve-all", label="Tous", layout="table", shared=True),
    )
    results = await view_svc.resolve_view(db_pool, ws, "resolve-all", _CALLER)
    assert len(results.rows) >= 1


async def test_resolve_view_filter_title(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    ws = "test-ws"
    await doc_svc.create_document(
        db_pool, ws, DocumentCreate(title="XYZ Spécifique", parent_id=None)
    )
    await view_svc.create_view(
        db_pool, ws, _CALLER,
        ViewCreate(
            slug="filter-title",
            label="Filtré titre",
            layout="table",
            shared=True,
            filter=[{"field": "@title", "op": "contains", "value": "Spécifique"}],
        ),
    )
    results = await view_svc.resolve_view(db_pool, ws, "filter-title", _CALLER)
    assert any(r.title == "XYZ Spécifique" for r in results.rows)


async def test_resolve_view_invalid_filter_op_raises(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    from fastapi import HTTPException
    ws = "test-ws"
    await view_svc.create_view(
        db_pool, ws, _CALLER,
        ViewCreate(
            slug="bad-op",
            label="Mauvais op",
            layout="table",
            shared=True,
            filter=[{"field": "@title", "op": "INVALID", "value": "x"}],
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await view_svc.resolve_view(db_pool, ws, "bad-op", _CALLER)
    assert exc.value.status_code == 422


async def test_view_layout_board_invalid(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    with pytest.raises(Exception):
        ViewCreate(slug="bad", label="Bad", layout="kanban")

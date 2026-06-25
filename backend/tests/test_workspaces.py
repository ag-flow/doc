from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from docflow.schemas.workspace import WorkspaceCreate, WorkspaceUpdate
from docflow.workspaces import service as ws_svc

# Tests de la couche service uniquement (DB requise)


async def test_create_workspace(db_pool: asyncpg.Pool) -> None:
    ws = await ws_svc.create_workspace(
        db_pool, WorkspaceCreate(slug="my-ws", label="My WS")
    )
    assert ws.slug == "my-ws"
    assert ws.description is None
    await db_pool.execute(
        "DELETE FROM workspace WHERE slug = $1", "my-ws"
    )


async def test_workspace_slug_unique(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="dup-ws", label="Dup"))
    with pytest.raises(HTTPException) as exc:
        await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="dup-ws", label="Dup2"))
    assert exc.value.status_code == 409
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "dup-ws")


async def test_workspace_slug_invalid() -> None:
    with pytest.raises(ValidationError):
        WorkspaceCreate(slug="UPPER", label="Bad")


async def test_list_workspaces(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    workspaces = await ws_svc.list_workspaces(db_pool)
    assert any(w.slug == "test-ws" for w in workspaces)


async def test_get_workspace_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await ws_svc.get_workspace(db_pool, "nonexistent")
    assert exc.value.status_code == 404


async def test_update_workspace(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    updated = await ws_svc.update_workspace(
        db_pool, "test-ws", WorkspaceUpdate(label="Updated Label")
    )
    assert updated.label == "Updated Label"
    assert updated.slug == "test-ws"


async def test_update_workspace_no_changes(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    original = await ws_svc.get_workspace(db_pool, "test-ws")
    result = await ws_svc.update_workspace(db_pool, "test-ws", WorkspaceUpdate())
    assert result.slug == original.slug


async def test_delete_workspace(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="to-delete", label="Del"))
    await ws_svc.delete_workspace(db_pool, "to-delete")
    with pytest.raises(HTTPException) as exc:
        await ws_svc.get_workspace(db_pool, "to-delete")
    assert exc.value.status_code == 404


async def test_delete_workspace_not_found(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await ws_svc.delete_workspace(db_pool, "ghost")
    assert exc.value.status_code == 404

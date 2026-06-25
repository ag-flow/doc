from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from docflow.auth.deps import require_admin, require_superadmin
from docflow.schemas.auth import AuthUser
from docflow.schemas.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from docflow.workspaces import service

router = APIRouter(tags=["workspaces"])

_Admin = Depends(require_admin)
_SuperAdmin = Depends(require_superadmin)


@router.get("/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(request: Request, _: AuthUser = _Admin) -> list[WorkspaceOut]:
    return await service.list_workspaces(request.app.state.pool)


@router.post("/workspaces", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    body: WorkspaceCreate, request: Request, _: AuthUser = _SuperAdmin
) -> WorkspaceOut:
    return await service.create_workspace(request.app.state.pool, body)


@router.get("/workspaces/{ws_slug}", response_model=WorkspaceOut)
async def get_workspace(ws_slug: str, request: Request, _: AuthUser = _Admin) -> WorkspaceOut:
    return await service.get_workspace(request.app.state.pool, ws_slug)


@router.patch("/workspaces/{ws_slug}", response_model=WorkspaceOut)
async def update_workspace(
    ws_slug: str, body: WorkspaceUpdate, request: Request, _: AuthUser = _SuperAdmin
) -> WorkspaceOut:
    return await service.update_workspace(request.app.state.pool, ws_slug, body)


@router.delete("/workspaces/{ws_slug}", status_code=204)
async def delete_workspace(
    ws_slug: str, request: Request, _: AuthUser = _SuperAdmin
) -> None:
    await service.delete_workspace(request.app.state.pool, ws_slug)

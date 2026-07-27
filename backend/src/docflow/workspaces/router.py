from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response

from docflow.auth.deps import (
    check_api_key_scope,
    filter_workspaces_by_scope,
    require_api_key_admin_write,
    require_authenticated,
)
from docflow.schemas.auth import AuthUser
from docflow.schemas.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from docflow.workspaces import service
from docflow.workspaces.access import accessible_workspace_slugs, require_ws_access

router = APIRouter(tags=["workspaces"], dependencies=[Depends(require_ws_access)])

_Auth = Depends(require_authenticated)


@router.get("/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(
    request: Request,
    include_archived: bool = Query(False),
    user: AuthUser = _Auth,
) -> list[WorkspaceOut]:
    result = await service.list_workspaces(
        request.app.state.pool, include_archived=include_archived
    )
    result = filter_workspaces_by_scope(request, result)
    # Utilisateur (JWT) non-admin : ne lister que ses workspaces (owner/membre).
    if getattr(request.state, "api_key_scopes", None) is None and not user.is_admin:
        allowed = await accessible_workspace_slugs(request.app.state.pool, user)
        if allowed is not None:
            result = [w for w in result if w.slug in allowed]
    return result


@router.post("/workspaces", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    body: WorkspaceCreate, request: Request, current_user: AuthUser = _Auth
) -> WorkspaceOut:
    require_api_key_admin_write(request)
    return await service.create_workspace(request.app.state.pool, body, current_user.id)


@router.get("/workspaces/{ws_slug}", response_model=WorkspaceOut)
async def get_workspace(ws_slug: str, request: Request, _: AuthUser = _Auth) -> WorkspaceOut:
    check_api_key_scope(request, ws_slug)
    return await service.get_workspace(request.app.state.pool, ws_slug)


@router.patch("/workspaces/{ws_slug}", response_model=WorkspaceOut)
async def update_workspace(
    ws_slug: str, body: WorkspaceUpdate, request: Request, _: AuthUser = _Auth
) -> WorkspaceOut:
    check_api_key_scope(request, ws_slug, write=True)
    return await service.update_workspace(request.app.state.pool, ws_slug, body)


@router.post("/workspaces/{ws_slug}/archive", response_model=WorkspaceOut)
async def archive_workspace(ws_slug: str, request: Request, _: AuthUser = _Auth) -> WorkspaceOut:
    check_api_key_scope(request, ws_slug, write=True)
    return await service.archive_workspace(request.app.state.pool, ws_slug)


@router.delete("/workspaces/{ws_slug}", status_code=204)
async def delete_workspace(
    ws_slug: str,
    request: Request,
    confirm: str = Query(..., description="Re-saisir le slug exact pour confirmer la purge"),
    _: AuthUser = _Auth,
) -> Response:
    check_api_key_scope(request, ws_slug, write=True)
    await service.delete_workspace(request.app.state.pool, ws_slug, confirm)
    return Response(status_code=204)

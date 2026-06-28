from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from docflow.auth.deps import get_current_user
from docflow.schemas.auth import AuthUser
from docflow.views import service
from docflow.views.service import ViewCreate, ViewOut, ViewResults, ViewUpdate

router = APIRouter(tags=["views"])

_Auth = Depends(get_current_user)


@router.get("/workspaces/{ws_slug}/views", response_model=list[ViewOut])
async def list_views(
    ws_slug: str,
    request: Request,
    current: AuthUser = _Auth,
) -> list[ViewOut]:
    return await service.list_views(request.app.state.pool, ws_slug, current.id)


@router.post("/workspaces/{ws_slug}/views", response_model=ViewOut, status_code=201)
async def create_view(
    ws_slug: str,
    data: ViewCreate,
    request: Request,
    current: AuthUser = _Auth,
) -> ViewOut:
    return await service.create_view(request.app.state.pool, ws_slug, current.id, data)


@router.get("/workspaces/{ws_slug}/views/{slug}", response_model=ViewOut)
async def get_view(
    ws_slug: str,
    slug: str,
    request: Request,
    current: AuthUser = _Auth,
) -> ViewOut:
    return await service.get_view(request.app.state.pool, ws_slug, slug, current.id)


@router.patch("/workspaces/{ws_slug}/views/{slug}", response_model=ViewOut)
async def update_view(
    ws_slug: str,
    slug: str,
    data: ViewUpdate,
    request: Request,
    current: AuthUser = _Auth,
) -> ViewOut:
    return await service.update_view(request.app.state.pool, ws_slug, slug, current.id, data)


@router.delete("/workspaces/{ws_slug}/views/{slug}", status_code=204)
async def delete_view(
    ws_slug: str,
    slug: str,
    request: Request,
    current: AuthUser = _Auth,
) -> None:
    await service.delete_view(request.app.state.pool, ws_slug, slug, current.id)


@router.get("/workspaces/{ws_slug}/views/{slug}/resolve", response_model=ViewResults)
async def resolve_view(
    ws_slug: str,
    slug: str,
    request: Request,
    current: AuthUser = _Auth,
    limit: int = Query(default=50, ge=1, le=200),
) -> ViewResults:
    return await service.resolve_view(
        request.app.state.pool, ws_slug, slug, current.id, limit=limit
    )

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request

from docflow.auth.deps import require_authenticated
from docflow.references import service
from docflow.references.service import (
    BacklinkOut,
    BrokenLinkBloc,
    BrokenLinkDetail,
    GlobalSearchResult,
)
from docflow.schemas.auth import AuthUser
from docflow.workspaces.access import accessible_workspace_slugs, require_ws_access

router = APIRouter(tags=["references"], dependencies=[Depends(require_ws_access)])

_Auth = Depends(require_authenticated)


@router.get(
    "/workspaces/{ws_slug}/documents/{doc_id}/backlinks",
    response_model=list[BacklinkOut],
)
async def get_backlinks(
    ws_slug: str,
    doc_id: uuid.UUID,
    request: Request,
    _: AuthUser = _Auth,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[BacklinkOut]:
    return await service.get_backlinks(request.app.state.pool, ws_slug, doc_id, limit)


@router.get(
    "/workspaces/{ws_slug}/broken-links",
    response_model=list[BrokenLinkBloc],
)
async def broken_links_by_bloc(
    ws_slug: str,
    request: Request,
    _: AuthUser = _Auth,
) -> list[BrokenLinkBloc]:
    return await service.broken_links_by_bloc(request.app.state.pool, ws_slug)


@router.get(
    "/workspaces/{ws_slug}/blocs/{bloc_id}/broken-links",
    response_model=list[BrokenLinkDetail],
)
async def broken_links_detail(
    ws_slug: str,
    bloc_id: uuid.UUID,
    request: Request,
    _: AuthUser = _Auth,
) -> list[BrokenLinkDetail]:
    return await service.broken_links_detail(request.app.state.pool, ws_slug, bloc_id)


@router.get("/search/documents", response_model=list[GlobalSearchResult])
async def search_documents_global(
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
    user: AuthUser = _Auth,
) -> list[GlobalSearchResult]:
    """Recherche par titre sur tous les workspaces accessibles à l'appelant."""
    allowed = await accessible_workspace_slugs(request.app.state.pool, user)
    return await service.search_documents_global(
        request.app.state.pool, q, limit, allowed_ws=allowed
    )

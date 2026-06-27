from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request

from docflow.auth.deps import require_admin
from docflow.references import service
from docflow.references.service import BrokenLinkBloc, BrokenLinkDetail, DocumentSearchResult
from docflow.schemas.auth import AuthUser

router = APIRouter(tags=["references"])

_Auth = Depends(require_admin)


@router.get(
    "/workspaces/{ws_slug}/documents/search",
    response_model=list[DocumentSearchResult],
)
async def search_documents(
    ws_slug: str,
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
    _: AuthUser = _Auth,
) -> list[DocumentSearchResult]:
    return await service.search_documents(request.app.state.pool, ws_slug, q, limit)


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

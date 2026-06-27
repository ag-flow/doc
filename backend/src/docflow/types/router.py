from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from docflow.auth.deps import require_admin
from docflow.schemas.auth import AuthUser
from docflow.schemas.types import (
    FunctionalTypeCreate,
    FunctionalTypeOut,
    FunctionalTypeRich,
    FunctionalTypeUpdate,
)
from docflow.types import service

router = APIRouter(tags=["types"])


@router.get("/workspaces/{ws_slug}/types/rich", response_model=list[FunctionalTypeRich])
async def list_types_rich(
    ws_slug: str,
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> list[FunctionalTypeRich]:
    """Retourne les types avec leurs propriétés et allowed_values."""
    return await service.list_types_rich(request.app.state.pool, ws_slug)


@router.get("/workspaces/{ws_slug}/types", response_model=list[FunctionalTypeOut])
async def list_types(
    ws_slug: str,
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> list[FunctionalTypeOut]:
    return await service.list_types(request.app.state.pool, ws_slug)


@router.post("/workspaces/{ws_slug}/types", response_model=FunctionalTypeOut, status_code=201)
async def create_type(
    ws_slug: str,
    body: FunctionalTypeCreate,
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> FunctionalTypeOut:
    return await service.create_type(request.app.state.pool, ws_slug, body)


@router.get("/workspaces/{ws_slug}/types/{type_slug}", response_model=FunctionalTypeOut)
async def get_type(
    ws_slug: str,
    type_slug: str,
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> FunctionalTypeOut:
    return await service.get_type(request.app.state.pool, ws_slug, type_slug)


@router.patch("/workspaces/{ws_slug}/types/{type_slug}", response_model=FunctionalTypeOut)
async def update_type(
    ws_slug: str,
    type_slug: str,
    body: FunctionalTypeUpdate,
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> FunctionalTypeOut:
    return await service.update_type(request.app.state.pool, ws_slug, type_slug, body)


@router.delete("/workspaces/{ws_slug}/types/{type_slug}", status_code=204)
async def delete_type(
    ws_slug: str,
    type_slug: str,
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> None:
    await service.delete_type(request.app.state.pool, ws_slug, type_slug)

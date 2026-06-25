from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from docflow.auth.deps import require_admin
from docflow.blocks import service
from docflow.schemas.auth import AuthUser
from docflow.schemas.block import DataBlockCreate, DataBlockOut, DataBlockUpdate

router = APIRouter(tags=["blocks"])

_WS = "/workspaces/{ws_slug}"
_BLOCK = _WS + "/blocks/{block_slug}"
_Auth = Depends(require_admin)


@router.get(_WS + "/blocks", response_model=list[DataBlockOut])
async def list_blocks(ws_slug: str, request: Request, _: AuthUser = _Auth) -> list[DataBlockOut]:
    return await service.list_blocks(request.app.state.pool, ws_slug)


@router.post(_WS + "/blocks", response_model=DataBlockOut, status_code=201)
async def create_block(
    ws_slug: str, body: DataBlockCreate, request: Request, _: AuthUser = _Auth
) -> DataBlockOut:
    return await service.create_block(request.app.state.pool, ws_slug, body)


@router.get(_BLOCK, response_model=DataBlockOut)
async def get_block(
    ws_slug: str, block_slug: str, request: Request, _: AuthUser = _Auth
) -> DataBlockOut:
    return await service.get_block(request.app.state.pool, ws_slug, block_slug)


@router.patch(_BLOCK, response_model=DataBlockOut)
async def update_block(
    ws_slug: str,
    block_slug: str,
    body: DataBlockUpdate,
    request: Request,
    _: AuthUser = _Auth,
) -> DataBlockOut:
    return await service.update_block(request.app.state.pool, ws_slug, block_slug, body)


@router.delete(_BLOCK, status_code=204)
async def delete_block(
    ws_slug: str, block_slug: str, request: Request, _: AuthUser = _Auth
) -> None:
    await service.delete_block(request.app.state.pool, ws_slug, block_slug)

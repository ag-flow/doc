from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, Query, Request

from docflow.auth.deps import require_admin
from docflow.blocks import service
from docflow.documents import service as doc_svc
from docflow.documents.block_ops import list_block_values as _list_block_values
from docflow.schemas.auth import AuthUser
from docflow.schemas.block import DataBlockCreate, DataBlockOut, DataBlockUpdate
from docflow.schemas.document import DocumentCreateInBlock, DocumentOut
from docflow.webhooks import service as wh_service

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


# ── Spec 23 : arbre du bloc ───────────────────────────────────────────────────


@router.get(_BLOCK + "/allowed-types", response_model=list[dict[str, str]])
async def get_allowed_types(
    ws_slug: str,
    block_slug: str,
    request: Request,
    _: AuthUser = _Auth,
    parent_id: uuid.UUID | None = Query(default=None),
) -> list[dict[str, str]]:
    return await doc_svc.allowed_types(request.app.state.pool, ws_slug, block_slug, parent_id)


@router.post(_BLOCK + "/documents", response_model=DocumentOut, status_code=201)
async def create_document_in_block(
    ws_slug: str,
    block_slug: str,
    body: DocumentCreateInBlock,
    request: Request,
    _: AuthUser = _Auth,
) -> DocumentOut:
    doc = await doc_svc.create_document_in_block(request.app.state.pool, ws_slug, block_slug, body)
    enc_key = request.app.state.settings.encryption_key
    asyncio.create_task(
        wh_service.emit_event(
            request.app.state.pool,
            ws_slug,
            "document.created",
            {
                "id": str(doc.doc_technical_key),
                "title": doc.title,
                "type": doc.type,
                "version": doc.version,
            },
            encryption_key=enc_key.reveal() if enc_key is not None else None,
        )
    )
    return doc


@router.get(_BLOCK + "/documents", response_model=list[DocumentOut])
async def list_block_documents(
    ws_slug: str,
    block_slug: str,
    request: Request,
    _: AuthUser = _Auth,
    prop_slug: str | None = Query(default=None),
    allowed_value_slug: str | None = Query(default=None),
) -> list[DocumentOut]:
    return await doc_svc.list_block_documents(
        request.app.state.pool,
        ws_slug,
        block_slug,
        prop_slug=prop_slug,
        allowed_value_slug=allowed_value_slug,
    )


@router.get(_BLOCK + "/values", response_model=dict[str, list[dict[str, object]]])
async def list_block_values(
    ws_slug: str,
    block_slug: str,
    request: Request,
    _: AuthUser = _Auth,
) -> dict[str, list[dict[str, object]]]:
    """Valeurs courantes de toutes les propriétés pour tous les docs du bloc (batch)."""
    return await _list_block_values(request.app.state.pool, ws_slug, block_slug)

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from docflow.auth.deps import require_admin
from docflow.documents import service
from docflow.schemas.auth import AuthUser
from docflow.schemas.document import DocumentCreate, DocumentOut, DocumentUpdate

router = APIRouter(tags=["documents"])

_WS = "/workspaces/{ws_slug}"
_DOC = _WS + "/documents/{doc_id}"
_Auth = Depends(require_admin)


@router.get(_WS + "/documents", response_model=list[DocumentOut])
async def list_documents(
    ws_slug: str, request: Request, _: AuthUser = _Auth
) -> list[DocumentOut]:
    return await service.list_documents(request.app.state.pool, ws_slug)


@router.post(_WS + "/documents", response_model=DocumentOut, status_code=201)
async def create_document(
    ws_slug: str, body: DocumentCreate, request: Request, _: AuthUser = _Auth
) -> DocumentOut:
    return await service.create_document(request.app.state.pool, ws_slug, body)


@router.get(_DOC, response_model=DocumentOut)
async def get_document(
    ws_slug: str, doc_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> DocumentOut:
    return await service.get_document(request.app.state.pool, ws_slug, doc_id)


@router.patch(_DOC, response_model=DocumentOut)
async def update_document(
    ws_slug: str,
    doc_id: uuid.UUID,
    body: DocumentUpdate,
    request: Request,
    _: AuthUser = _Auth,
) -> DocumentOut:
    return await service.update_document(request.app.state.pool, ws_slug, doc_id, body)


@router.delete(_DOC, status_code=204)
async def delete_document(
    ws_slug: str, doc_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> None:
    await service.delete_document(request.app.state.pool, ws_slug, doc_id)

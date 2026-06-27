from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from docflow.auth.deps import require_admin
from docflow.documents import service
from docflow.references import service as ref_service
from docflow.references.service import DocumentSearchResult
from docflow.schemas.auth import AuthUser
from docflow.schemas.document import DocumentCreate, DocumentOut, DocumentUpdate
from docflow.schemas.property_value import PropertyValueOut, PropertyValueSet
from docflow.webhooks import service as wh_service

router = APIRouter(tags=["documents"])

_WS = "/workspaces/{ws_slug}"
_DOC = _WS + "/documents/{doc_id}"
_Auth = Depends(require_admin)


def _enc_key(request: Request) -> str | None:
    key = request.app.state.settings.encryption_key
    return key.reveal() if key is not None else None


def _fire(request: Request, event: str, ws_slug: str, snapshot: dict[str, Any]) -> None:
    """Lance l'émission webhook en fire-and-forget."""
    asyncio.create_task(
        wh_service.emit_event(
            request.app.state.pool,
            ws_slug,
            event,
            snapshot,
            encryption_key=_enc_key(request),
        )
    )


class _ChangeEntry(BaseModel):
    seq: int
    nature: str
    document_id: str
    occurred_at: str


class _ChangeFeedOut(BaseModel):
    changes: list[_ChangeEntry]
    next_cursor: int
    has_more: bool


@router.get(_WS + "/documents", response_model=list[DocumentOut])
async def list_documents(
    ws_slug: str,
    request: Request,
    _: AuthUser = _Auth,
    functional_type: str | None = Query(default=None),
    prop_slug: str | None = Query(default=None),
    allowed_value_slug: str | None = Query(default=None),
) -> list[DocumentOut]:
    return await service.list_documents(
        request.app.state.pool,
        ws_slug,
        functional_type=functional_type,
        prop_slug=prop_slug,
        allowed_value_slug=allowed_value_slug,
    )


@router.post(_WS + "/documents", response_model=DocumentOut, status_code=201)
async def create_document(
    ws_slug: str, body: DocumentCreate, request: Request, _: AuthUser = _Auth
) -> DocumentOut:
    doc = await service.create_document(request.app.state.pool, ws_slug, body)
    _fire(
        request,
        "document.created",
        ws_slug,
        {
            "id": str(doc.doc_technical_key),
            "title": doc.title,
            "type": doc.type,
            "version": doc.version,
        },
    )
    return doc


@router.get(_WS + "/documents/search", response_model=list[DocumentSearchResult])
async def search_documents(
    ws_slug: str,
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
    _: AuthUser = _Auth,
) -> list[DocumentSearchResult]:
    return await ref_service.search_documents(request.app.state.pool, ws_slug, q, limit)


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
    doc = await service.update_document(request.app.state.pool, ws_slug, doc_id, body)
    _fire(
        request,
        "document.updated",
        ws_slug,
        {
            "id": str(doc.doc_technical_key),
            "title": doc.title,
            "type": doc.type,
            "version": doc.version,
        },
    )
    return doc


class _ExposedUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    exposed: bool


@router.patch(_DOC + "/exposed", response_model=DocumentOut)
async def set_document_exposed(
    ws_slug: str,
    doc_id: uuid.UUID,
    body: _ExposedUpdate,
    request: Request,
    _: AuthUser = _Auth,
) -> DocumentOut:
    return await service.set_document_exposed(request.app.state.pool, ws_slug, doc_id, body.exposed)


@router.delete(_DOC, status_code=204)
async def delete_document(
    ws_slug: str, doc_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> None:
    snapshot = await service.delete_document(request.app.state.pool, ws_slug, doc_id)
    _fire(request, "document.deleted", ws_slug, snapshot)


@router.get(_WS + "/changes", response_model=_ChangeFeedOut)
async def get_changes(
    ws_slug: str,
    request: Request,
    _: AuthUser = _Auth,
    since: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> _ChangeFeedOut:
    async with request.app.state.pool.acquire() as conn:
        from docflow.db.helpers import require_workspace

        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            "SELECT seq, nature, document_ref, occurred_at "
            "FROM document_change_log "
            "WHERE workspace_technical_key = $1 AND seq > $2 "
            "ORDER BY seq LIMIT $3",
            wk,
            since,
            limit + 1,
        )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = int(page[-1]["seq"]) if page else since
    return _ChangeFeedOut(
        changes=[
            _ChangeEntry(
                seq=int(r["seq"]),
                nature=r["nature"],
                document_id=str(r["document_ref"]),
                occurred_at=r["occurred_at"].isoformat(),
            )
            for r in page
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ── Property values ───────────────────────────────────────────────────────────

_VAL = _DOC + "/values"


@router.get(_VAL, response_model=list[PropertyValueOut])
async def list_property_values(
    ws_slug: str, doc_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> list[PropertyValueOut]:
    return await service.list_property_values(request.app.state.pool, ws_slug, doc_id)


@router.put(_VAL + "/{prop_slug}", response_model=PropertyValueOut)
async def set_property_value(
    ws_slug: str,
    doc_id: uuid.UUID,
    prop_slug: str,
    body: PropertyValueSet,
    request: Request,
    _: AuthUser = _Auth,
) -> PropertyValueOut:
    return await service.set_property_value(
        request.app.state.pool, ws_slug, doc_id, prop_slug, body
    )


@router.delete(_VAL + "/{prop_slug}", status_code=204)
async def delete_property_value(
    ws_slug: str, doc_id: uuid.UUID, prop_slug: str, request: Request, _: AuthUser = _Auth
) -> None:
    await service.delete_property_value(request.app.state.pool, ws_slug, doc_id, prop_slug)

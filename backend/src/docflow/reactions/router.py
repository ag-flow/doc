from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from docflow.auth.deps import require_admin
from docflow.reactions import service
from docflow.reactions.service import CommentCreate, CommentOut, ReactionOut, ReactionSet
from docflow.schemas.auth import AuthUser

router = APIRouter(tags=["reactions"])

_WS = "/workspaces/{ws_slug}"
_DOC = _WS + "/documents/{doc_id}"
_CMT = _DOC + "/comments/{comment_id}"
_Auth = Depends(require_admin)


# ── Réactions sur document ────────────────────────────────────────────────────


@router.get(_DOC + "/reactions", response_model=ReactionOut)
async def get_doc_reactions(
    ws_slug: str, doc_id: uuid.UUID, request: Request, user: AuthUser = _Auth
) -> ReactionOut:
    return await service.get_doc_reactions(request.app.state.pool, ws_slug, doc_id, user.id)


@router.put(_DOC + "/reaction", response_model=ReactionOut)
async def toggle_doc_reaction(
    ws_slug: str,
    doc_id: uuid.UUID,
    body: ReactionSet,
    request: Request,
    user: AuthUser = _Auth,
) -> ReactionOut:
    return await service.toggle_doc_reaction(
        request.app.state.pool, ws_slug, doc_id, user.id, body.nature
    )


@router.delete(_DOC + "/reaction", response_model=ReactionOut)
async def remove_doc_reaction(
    ws_slug: str, doc_id: uuid.UUID, request: Request, user: AuthUser = _Auth
) -> ReactionOut:
    return await service.remove_doc_reaction(request.app.state.pool, ws_slug, doc_id, user.id)


# ── Commentaires ─────────────────────────────────────────────────────────────


@router.get(_DOC + "/comments", response_model=list[CommentOut])
async def list_comments(
    ws_slug: str, doc_id: uuid.UUID, request: Request, user: AuthUser = _Auth
) -> list[CommentOut]:
    return await service.list_comments(request.app.state.pool, ws_slug, doc_id, user.id)


@router.post(_DOC + "/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    ws_slug: str,
    doc_id: uuid.UUID,
    body: CommentCreate,
    request: Request,
    user: AuthUser = _Auth,
) -> CommentOut:
    return await service.add_comment(
        request.app.state.pool, ws_slug, doc_id, user.id, user.label, body.body
    )


@router.delete(_CMT, status_code=204)
async def delete_comment(
    ws_slug: str,
    doc_id: uuid.UUID,
    comment_id: uuid.UUID,
    request: Request,
    user: AuthUser = _Auth,
) -> None:
    await service.delete_comment(
        request.app.state.pool, ws_slug, doc_id, comment_id, user.id, user.is_admin
    )


# ── Réactions sur commentaires ────────────────────────────────────────────────


@router.put(_CMT + "/reaction", response_model=ReactionOut)
async def toggle_comment_reaction(
    ws_slug: str,
    doc_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: ReactionSet,
    request: Request,
    user: AuthUser = _Auth,
) -> ReactionOut:
    return await service.toggle_comment_reaction(
        request.app.state.pool, ws_slug, doc_id, comment_id, user.id, body.nature
    )


@router.delete(_CMT + "/reaction", response_model=ReactionOut)
async def remove_comment_reaction(
    ws_slug: str,
    doc_id: uuid.UUID,
    comment_id: uuid.UUID,
    request: Request,
    user: AuthUser = _Auth,
) -> ReactionOut:
    return await service.remove_comment_reaction(
        request.app.state.pool, ws_slug, doc_id, comment_id, user.id
    )

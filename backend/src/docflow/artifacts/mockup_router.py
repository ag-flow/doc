"""REST — base CSS des maquettes (mockup-base) : set / get / apply / propagate / drift.

Le patch d'artefact n'avait jusqu'ici aucune surface REST (MCP seulement) ; ces
endpoints exposent le cycle complet de la base côté HTTP, pour une orchestration
hors-agent. Les mêmes primitives que MCP (mockup_base.*), donc parité stricte.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from docflow.artifacts import mockup_base as mb
from docflow.auth.deps import check_api_key_scope, require_authenticated
from docflow.schemas.auth import AuthUser
from docflow.workspaces.access import require_ws_access

router = APIRouter(tags=["mockup-base"], dependencies=[Depends(require_ws_access)])

_WS = "/workspaces/{ws_slug}"
_BASE = _WS + "/mockup-bases/{base_id}"
_Auth = Depends(require_authenticated)


class _CssBody(BaseModel):
    model_config = {"extra": "forbid"}
    css: str


class _UpdateBody(BaseModel):
    model_config = {"extra": "forbid"}
    css: str
    if_revision: int


class _ApplyBody(BaseModel):
    model_config = {"extra": "forbid"}
    maquette_id: uuid.UUID


@router.post(_WS + "/mockup-bases", status_code=201)
async def create_base(
    ws_slug: str, body: _CssBody, request: Request, user: AuthUser = _Auth
) -> dict[str, object]:
    check_api_key_scope(request, ws_slug, write=True)
    return await mb.set_mockup_base(
        request.app.state.pool,
        ws_slug,
        css=body.css,
        updated_by=user.id,
        max_bytes=request.app.state.settings.artifact_max_bytes,
    )


@router.get(_BASE)
async def get_base(
    ws_slug: str, base_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> dict[str, object]:
    check_api_key_scope(request, ws_slug)
    return await mb.get_mockup_base(request.app.state.pool, ws_slug, base_id)


@router.put(_BASE)
async def update_base(
    ws_slug: str, base_id: uuid.UUID, body: _UpdateBody, request: Request, user: AuthUser = _Auth
) -> dict[str, object]:
    check_api_key_scope(request, ws_slug, write=True)
    return await mb.set_mockup_base(
        request.app.state.pool,
        ws_slug,
        css=body.css,
        updated_by=user.id,
        max_bytes=request.app.state.settings.artifact_max_bytes,
        base_id=base_id,
        if_revision=body.if_revision,
    )


@router.post(_BASE + "/apply")
async def apply_base(
    ws_slug: str, base_id: uuid.UUID, body: _ApplyBody, request: Request, user: AuthUser = _Auth
) -> dict[str, object]:
    check_api_key_scope(request, ws_slug, write=True)
    return await mb.apply_mockup_base(
        request.app.state.pool,
        ws_slug,
        maquette_id=body.maquette_id,
        base_id=base_id,
        updated_by=user.id,
        max_bytes=request.app.state.settings.artifact_max_bytes,
    )


@router.post(_BASE + "/propagate")
async def propagate_base(
    ws_slug: str, base_id: uuid.UUID, request: Request, user: AuthUser = _Auth
) -> dict[str, object]:
    check_api_key_scope(request, ws_slug, write=True)
    return await mb.propagate_mockup_base(
        request.app.state.pool,
        ws_slug,
        base_id,
        updated_by=user.id,
        max_bytes=request.app.state.settings.artifact_max_bytes,
    )


@router.get(_BASE + "/drift")
async def drift_base(
    ws_slug: str, base_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> dict[str, object]:
    check_api_key_scope(request, ws_slug)
    return await mb.mockup_base_drift(request.app.state.pool, ws_slug, base_id)

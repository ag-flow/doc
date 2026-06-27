from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request

from docflow.auth.deps import require_admin
from docflow.automations import service
from docflow.schemas.auth import AuthUser
from docflow.schemas.automations import (
    AutomationCreate,
    AutomationOut,
    AutomationRunOut,
    AutomationUpdate,
)

router = APIRouter(tags=["automations"])

_WS = "/workspaces/{ws_slug}"
_AUTO = _WS + "/automations/{automation_id}"
_Auth = Depends(require_admin)


@router.get(_WS + "/automations", response_model=list[AutomationOut])
async def list_automations(
    ws_slug: str, request: Request, _: AuthUser = _Auth
) -> list[AutomationOut]:
    return await service.list_automations(request.app.state.pool, ws_slug)


@router.post(_WS + "/automations", response_model=AutomationOut, status_code=201)
async def create_automation(
    ws_slug: str, body: AutomationCreate, request: Request, _: AuthUser = _Auth
) -> AutomationOut:
    return await service.create_automation(request.app.state.pool, ws_slug, body)


@router.get(_AUTO, response_model=AutomationOut)
async def get_automation(
    ws_slug: str, automation_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> AutomationOut:
    return await service.get_automation(request.app.state.pool, ws_slug, automation_id)


@router.patch(_AUTO, response_model=AutomationOut)
async def update_automation(
    ws_slug: str,
    automation_id: uuid.UUID,
    body: AutomationUpdate,
    request: Request,
    _: AuthUser = _Auth,
) -> AutomationOut:
    return await service.update_automation(
        request.app.state.pool, ws_slug, automation_id, body
    )


@router.delete(_AUTO, status_code=204)
async def delete_automation(
    ws_slug: str, automation_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> None:
    await service.delete_automation(request.app.state.pool, ws_slug, automation_id)


@router.get(_AUTO + "/runs", response_model=list[AutomationRunOut])
async def list_runs(
    ws_slug: str,
    automation_id: uuid.UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    _: AuthUser = _Auth,
) -> list[AutomationRunOut]:
    return await service.list_runs(
        request.app.state.pool, ws_slug, automation_id, limit
    )


@router.post(_AUTO + "/runs/{run_id}/replay", response_model=AutomationRunOut)
async def replay_run(
    ws_slug: str,
    automation_id: uuid.UUID,
    run_id: uuid.UUID,
    request: Request,
    _: AuthUser = _Auth,
) -> AutomationRunOut:
    return await service.replay_run(
        request.app.state.pool,
        ws_slug,
        automation_id,
        run_id,
        request.app.state.settings,
    )

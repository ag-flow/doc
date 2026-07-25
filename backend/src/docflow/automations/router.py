from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request

from docflow.auth.deps import require_authenticated
from docflow.automations import service
from docflow.schemas.auth import AuthUser
from docflow.schemas.automations import (
    AutomationCreate,
    AutomationOrderIn,
    AutomationOut,
    AutomationRunOut,
    AutomationUpdate,
)

router = APIRouter(tags=["automations"])

_WS = "/workspaces/{ws_slug}"
_AUTO = _WS + "/automations/{automation_id}"
_Auth = Depends(require_authenticated)


@router.get(_WS + "/automations", response_model=list[AutomationOut])
async def list_automations(
    ws_slug: str, request: Request, _: AuthUser = _Auth
) -> list[AutomationOut]:
    return await service.list_automations(request.app.state.pool, ws_slug)


@router.put(_WS + "/automations/order", response_model=list[AutomationOut])
async def reorder_automations(
    ws_slug: str, body: AutomationOrderIn, request: Request, _: AuthUser = _Auth
) -> list[AutomationOut]:
    """Ordre d'évaluation des automates du workspace (drag & drop)."""
    return await service.reorder_automations(request.app.state.pool, ws_slug, body.ids)


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
    return await service.update_automation(request.app.state.pool, ws_slug, automation_id, body)


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
    return await service.list_runs(request.app.state.pool, ws_slug, automation_id, limit)


@router.post(_AUTO + "/clone", response_model=AutomationOut, status_code=201)
async def clone_automation(
    ws_slug: str, automation_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> AutomationOut:
    """Clone l'automate (config + portée + headers), créé désactivé."""
    return await service.clone_automation(request.app.state.pool, ws_slug, automation_id)


@router.post(_AUTO + "/run-next")
async def run_next(
    ws_slug: str, automation_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> dict[str, object]:
    """Joue le prochain event en attente SANS avancer le curseur (test)."""
    return await service.run_next_pending(
        request.app.state.pool, ws_slug, automation_id, request.app.state.settings
    )


@router.post(_AUTO + "/advance")
async def advance(
    ws_slug: str, automation_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> dict[str, object]:
    """Joue l'event courant ET avance le curseur (pas manuel)."""
    return await service.advance_pending(
        request.app.state.pool, ws_slug, automation_id, request.app.state.settings
    )


@router.post(_AUTO + "/cursor-back")
async def cursor_back(
    ws_slug: str, automation_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> dict[str, object]:
    """Recule le curseur d'un event (l'event précédent redevient courant)."""
    return await service.cursor_back(request.app.state.pool, ws_slug, automation_id)


@router.delete(_AUTO + "/runs", status_code=200)
async def clear_runs(
    ws_slug: str, automation_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> dict[str, int]:
    """Vide l'historique d'exécutions de l'automate."""
    deleted = await service.clear_runs(request.app.state.pool, ws_slug, automation_id)
    return {"deleted": deleted}


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

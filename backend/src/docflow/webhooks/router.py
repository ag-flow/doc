from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from docflow.auth.deps import require_authenticated
from docflow.schemas.auth import AuthUser
from docflow.schemas.webhook import WebhookCreate, WebhookOut, WebhookTestOut, WebhookUpdate
from docflow.vault import service as vault_svc
from docflow.webhooks import service
from docflow.workspaces.access import require_ws_access

router = APIRouter(tags=["webhooks"], dependencies=[Depends(require_ws_access)])

_WS = "/workspaces/{ws_slug}"
_WH = _WS + "/webhooks/{webhook_id}"
_Auth = Depends(require_authenticated)


def _key(request: Request) -> str | None:
    key = request.app.state.settings.encryption_key
    return key.reveal() if key is not None else None


async def _assert_header_secrets_owned(
    request: Request, headers: dict[str, str] | None, owner_id: uuid.UUID
) -> None:
    """Isolation des secrets (STANDARD Gestion des secrets §1/§6) : une valeur de
    header ${secret://}/${hmac://} doit appartenir à l'agissant. Validé au
    routeur (l'identité y est présente). None = pas de headers dans le body."""
    if headers is None:
        return
    refs = list(headers.values())
    await vault_svc.assert_refs_owned(request.app.state.pool, refs, owner_id)
    # Résolubilité à la configuration (STANDARD Harpocrate §6).
    await vault_svc.assert_refs_resolvable(request.app.state.pool, refs)


@router.get(_WS + "/webhooks", response_model=list[WebhookOut])
async def list_webhooks(ws_slug: str, request: Request, _: AuthUser = _Auth) -> list[WebhookOut]:
    return await service.list_webhooks(
        request.app.state.pool, ws_slug, encryption_key=_key(request)
    )


@router.post(_WS + "/webhooks", response_model=WebhookOut, status_code=201)
async def create_webhook(
    ws_slug: str, body: WebhookCreate, request: Request, user: AuthUser = _Auth
) -> WebhookOut:
    await _assert_header_secrets_owned(request, body.headers, user.id)
    return await service.create_webhook(
        request.app.state.pool, ws_slug, body, encryption_key=_key(request)
    )


@router.get(_WH, response_model=WebhookOut)
async def get_webhook(
    ws_slug: str, webhook_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> WebhookOut:
    return await service.get_webhook(
        request.app.state.pool, ws_slug, webhook_id, encryption_key=_key(request)
    )


@router.patch(_WH, response_model=WebhookOut)
async def update_webhook(
    ws_slug: str,
    webhook_id: uuid.UUID,
    body: WebhookUpdate,
    request: Request,
    user: AuthUser = _Auth,
) -> WebhookOut:
    await _assert_header_secrets_owned(request, body.headers, user.id)
    return await service.update_webhook(
        request.app.state.pool, ws_slug, webhook_id, body, encryption_key=_key(request)
    )


@router.delete(_WH, status_code=204)
async def delete_webhook(
    ws_slug: str, webhook_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> None:
    await service.delete_webhook(request.app.state.pool, ws_slug, webhook_id)


@router.post(_WH + "/test", response_model=WebhookTestOut)
async def test_webhook(
    ws_slug: str, webhook_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> WebhookTestOut:
    status_code, error, duration_ms = await service.test_webhook(
        request.app.state.pool, ws_slug, webhook_id, encryption_key=_key(request)
    )
    return WebhookTestOut(status_code=status_code, error=error, duration_ms=duration_ms)

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from docflow.auth.deps import require_superadmin
from docflow.oidc import service
from docflow.schemas.auth import AuthUser
from docflow.schemas.oidc import OidcConfigOut, OidcConfigSet, OidcPublicConfig

router = APIRouter(tags=["oidc"])

_SuperAdmin = Depends(require_superadmin)


@router.get("/admin/oidc", response_model=OidcConfigOut | None)
async def get_oidc_config(request: Request, _: AuthUser = _SuperAdmin) -> OidcConfigOut | None:
    return await service.get_oidc_config(request.app.state.pool)


@router.put("/admin/oidc", response_model=OidcConfigOut)
async def set_oidc_config(
    body: OidcConfigSet, request: Request, _: AuthUser = _SuperAdmin
) -> OidcConfigOut:
    return await service.set_oidc_config(request.app.state.pool, body)


@router.get("/auth/oidc/config", response_model=OidcPublicConfig | None)
async def get_public_oidc_config(request: Request) -> OidcPublicConfig | None:
    return await service.get_public_config(request.app.state.pool)


@router.post("/auth/oidc/callback")
async def oidc_callback(body: dict[str, object], request: Request) -> dict[str, str]:
    """Reçoit les claims id_token (après vérification externe) et émet un JWT docflow."""
    settings = request.app.state.settings
    token = await service.handle_oidc_callback(
        request.app.state.pool,
        settings.jwt_secret.reveal(),
        body,
    )
    return {"access_token": token, "token_type": "bearer"}

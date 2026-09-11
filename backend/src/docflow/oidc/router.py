from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from docflow.auth.cookies import set_session_cookie
from docflow.auth.deps import require_superadmin
from docflow.oidc import service
from docflow.schemas.auth import AuthUser
from docflow.schemas.oidc import OidcCallbackIn, OidcConfigOut, OidcConfigSet, OidcPublicConfig

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
    return await service.get_login_config(request.app.state.pool)


@router.post("/auth/oidc/callback", response_model=AuthUser)
async def oidc_callback(body: OidcCallbackIn, request: Request, response: Response) -> AuthUser:
    """Échange le code OIDC côté serveur, vérifie l'id_token, ouvre une session
    serveur et pose le cookie (n'émet plus de JWT docflow)."""
    settings = request.app.state.settings
    pool = request.app.state.pool
    user = await service.handle_oidc_callback(pool, settings, body)
    async with pool.acquire() as conn:
        await set_session_cookie(
            response,
            conn,
            user.id,
            secure=settings.session_cookie_secure,
            max_age=settings.session_idle_ttl_seconds,
        )
    return user

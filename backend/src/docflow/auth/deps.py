from __future__ import annotations

import uuid

import asyncpg
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from docflow.auth.jwt import decode_token, user_id_from_claims
from docflow.schemas.auth import AuthUser

_bearer = HTTPBearer(auto_error=False)

_SELECT_USER = """
SELECT id, email, label, is_admin, validated, disabled
FROM app_user WHERE id = $1
"""


def _pool(request: Request) -> asyncpg.Pool:
    pool: asyncpg.Pool = request.app.state.pool
    return pool


def _jwt_secret(request: Request) -> str:
    secret: str = request.app.state.settings.jwt_secret.reveal()
    return secret


async def _resolve_jwt(
    request: Request, credentials: HTTPAuthorizationCredentials
) -> AuthUser:
    try:
        claims = decode_token(credentials.credentials, _jwt_secret(request))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="token invalide ou expiré") from exc

    user_id: uuid.UUID = user_id_from_claims(claims)
    pool: asyncpg.Pool = _pool(request)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT_USER, user_id)

    if row is None or row["disabled"]:
        raise HTTPException(status_code=401, detail="compte désactivé ou introuvable")

    if not row["validated"]:
        raise HTTPException(status_code=403, detail="PendingValidation")

    return AuthUser(
        id=row["id"],
        email=row["email"],
        label=row["label"],
        is_admin=row["is_admin"],
        validated=row["validated"],
        disabled=row["disabled"],
    )


async def _resolve_api_key(
    request: Request, credentials: HTTPAuthorizationCredentials
) -> AuthUser:
    from docflow.apikeys.service import resolve_api_key

    user, scopes, profile_is_admin = await resolve_api_key(
        _pool(request), credentials.credentials
    )
    request.state.api_key_scopes = scopes
    request.state.api_key_is_admin = profile_is_admin
    return user


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="token manquant")

    if credentials.credentials.startswith("dfk_"):
        return await _resolve_api_key(request, credentials)

    return await _resolve_jwt(request, credentials)


async def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return user


async def require_superadmin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="droits admin requis")
    return user


def _is_api_key_admin(request: Request) -> bool:
    return bool(getattr(request.state, "api_key_is_admin", False))


def _is_api_key_request(request: Request) -> bool:
    return getattr(request.state, "api_key_scopes", None) is not None


def check_api_key_scope(
    request: Request,
    ws_slug: str,
    block_slug: str | None = None,
    write: bool = False,
) -> None:
    """Lève 403 si la requête vient d'une API key et que le scope demandé est refusé.

    Sans effet pour les requêtes JWT et pour les clés API de profil admin.
    """
    from docflow.apikeys.schemas import ApiProfileScopeOut

    scopes: list[ApiProfileScopeOut] | None = getattr(
        request.state, "api_key_scopes", None
    )
    if scopes is None:
        return  # JWT → accès complet
    if _is_api_key_admin(request):
        return  # profil admin → accès complet

    for scope in scopes:
        if scope.workspace_slug != ws_slug:
            continue
        if scope.block_slug is not None and scope.block_slug != block_slug:
            continue
        if write and scope.read_only:
            continue
        return

    raise HTTPException(status_code=403, detail="hors du périmètre de la clé API")


def require_api_key_admin_write(request: Request) -> None:
    """Bloque les clés API non-admin sur les opérations structurelles (sans scope ws connu).

    Opérations visées : create_workspace, import_template.
    Sans effet pour les JWT et les clés de profil admin.
    """
    if not _is_api_key_request(request):
        return  # JWT → libre
    if not _is_api_key_admin(request):
        raise HTTPException(
            status_code=403,
            detail="clé API non-admin : opération d'administration interdite",
        )


def filter_workspaces_by_scope(request: Request, workspaces: list) -> list:  # type: ignore[type-arg]
    """Filtre la liste des workspaces selon les scopes de l'API key (sans effet si JWT/admin)."""
    from docflow.apikeys.schemas import ApiProfileScopeOut

    scopes: list[ApiProfileScopeOut] | None = getattr(
        request.state, "api_key_scopes", None
    )
    if scopes is None or _is_api_key_admin(request):
        return workspaces
    allowed = {s.workspace_slug for s in scopes}
    return [ws for ws in workspaces if ws.slug in allowed]


def filter_blocks_by_scope(
    request: Request, ws_slug: str, blocks: list  # type: ignore[type-arg]
) -> list:  # type: ignore[type-arg]
    """Filtre la liste des blocs selon les scopes de l'API key (sans effet si JWT/admin)."""
    from docflow.apikeys.schemas import ApiProfileScopeOut

    scopes: list[ApiProfileScopeOut] | None = getattr(
        request.state, "api_key_scopes", None
    )
    if scopes is None or _is_api_key_admin(request):
        return blocks
    ws_scopes = [s for s in scopes if s.workspace_slug == ws_slug]
    if not ws_scopes:
        return []
    if any(s.block_slug is None for s in ws_scopes):
        return blocks
    allowed = {s.block_slug for s in ws_scopes}
    return [b for b in blocks if b.slug in allowed]

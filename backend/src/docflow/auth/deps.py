from __future__ import annotations

import uuid

import asyncpg
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from docflow.auth.jwt import decode_token, user_id_from_claims
from docflow.schemas.auth import AuthUser

_bearer = HTTPBearer(auto_error=False)

_SELECT_USER = """
SELECT id, email, label, is_superadmin, disabled
FROM admin_user WHERE id = $1
"""


def _pool(request: Request) -> asyncpg.Pool:
    pool: asyncpg.Pool = request.app.state.pool
    return pool


def _jwt_secret(request: Request) -> str:
    secret: str = request.app.state.settings.jwt_secret.reveal()
    return secret


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="token manquant")

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

    return AuthUser(
        id=row["id"],
        email=row["email"],
        label=row["label"],
        is_superadmin=row["is_superadmin"],
        disabled=row["disabled"],
    )


async def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return user


async def require_superadmin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="droits superadmin requis")
    return user

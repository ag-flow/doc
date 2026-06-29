from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from docflow.auth.deps import require_admin
from docflow.auth.jwt import create_token
from docflow.auth.password import verify_password
from docflow.oidc import service as oidc_service
from docflow.schemas.auth import AuthUser, LoginRequest, TokenResponse
from docflow.schemas.setup import AuthMethodsOut
from docflow.setup import service as setup_service

router = APIRouter(prefix="/auth", tags=["auth"])

_SELECT_FOR_LOGIN = """
SELECT id, email, label, password_hash, is_admin, validated, disabled
FROM app_user WHERE email = $1
"""


@router.get("/methods", response_model=AuthMethodsOut)
async def auth_methods(request: Request) -> AuthMethodsOut:
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        count = await setup_service.user_count(conn)
        oidc_cfg = await oidc_service.get_public_config(pool)
    return AuthMethodsOut(
        local=True,
        oidc=oidc_cfg is not None,
        needs_setup=count == 0,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request) -> TokenResponse:
    pool = request.app.state.pool
    secret: str = request.app.state.settings.jwt_secret.reveal()

    async with pool.acquire() as conn:
        count = await setup_service.user_count(conn)
        if count == 0:
            raise HTTPException(status_code=503, detail="SetupRequired")
        row = await conn.fetchrow(_SELECT_FOR_LOGIN, body.email)

    _invalid = HTTPException(status_code=401, detail="identifiants invalides")

    if row is None or row["password_hash"] is None or row["disabled"]:
        raise _invalid

    if not verify_password(body.password, row["password_hash"]):
        raise _invalid

    if not row["validated"]:
        raise HTTPException(status_code=403, detail="PendingValidation")

    user = AuthUser(
        id=row["id"],
        email=row["email"],
        label=row["label"],
        is_admin=row["is_admin"],
        validated=row["validated"],
        disabled=row["disabled"],
    )
    return TokenResponse(access_token=create_token(user, secret))


@router.get("/me", response_model=AuthUser)
async def me(user: AuthUser = Depends(require_admin)) -> AuthUser:
    return user

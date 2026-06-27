from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from docflow.auth.deps import require_admin
from docflow.auth.jwt import create_token
from docflow.auth.password import verify_password
from docflow.schemas.auth import AuthUser, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_SELECT_FOR_LOGIN = """
SELECT id, email, label, password_hash, is_superadmin, disabled
FROM admin_user WHERE email = $1
"""


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request) -> TokenResponse:
    pool = request.app.state.pool
    secret: str = request.app.state.settings.jwt_secret.reveal()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT_FOR_LOGIN, body.email)

    # Message non discriminant — même réponse pour email inconnu, mauvais mdp, compte désactivé
    _invalid = HTTPException(status_code=401, detail="identifiants invalides")

    if row is None or row["password_hash"] is None or row["disabled"]:
        raise _invalid

    if not verify_password(body.password, row["password_hash"]):
        raise _invalid

    user = AuthUser(
        id=row["id"],
        email=row["email"],
        label=row["label"],
        is_superadmin=row["is_superadmin"],
        disabled=row["disabled"],
    )
    return TokenResponse(access_token=create_token(user, secret))


@router.get("/me", response_model=AuthUser)
async def me(user: AuthUser = Depends(require_admin)) -> AuthUser:
    return user

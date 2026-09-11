from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from docflow.auth.cookies import delete_session_cookie, set_session_cookie
from docflow.auth.deps import require_authenticated
from docflow.auth.password import DUMMY_PASSWORD_HASH, verify_password
from docflow.auth.sessions import revoke_session, session_cookie_name
from docflow.oidc import service as oidc_service
from docflow.schemas.auth import AuthUser, LoginRequest
from docflow.schemas.setup import AuthMethodsOut
from docflow.setup import service as setup_service

router = APIRouter(prefix="/auth", tags=["auth"])

_SELECT_FOR_LOGIN = """
SELECT id, email, label, password_hash, is_admin, validated, disabled
FROM app_user WHERE email = $1
"""


async def _local_login_enabled(request: Request) -> bool:
    """État effectif de la connexion locale.

    Priorité : surcharge env LOCAL_LOGIN_ENABLED (break-glass fichier) si
    définie, sinon réglage de la config OIDC — qui n'a d'effet que si l'OIDC
    est activé : désactiver l'OIDC réactive automatiquement le local.
    """
    override: bool | None = request.app.state.settings.local_login_enabled
    if override is not None:
        return override
    return not await oidc_service.local_login_disabled_by_oidc(request.app.state.pool)


@router.get("/methods", response_model=AuthMethodsOut)
async def auth_methods(request: Request) -> AuthMethodsOut:
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        count = await setup_service.user_count(conn)
        oidc_cfg = await oidc_service.get_public_config(pool)
    # Réglage de la page OIDC (effectif seulement si l'OIDC est activé),
    # surchargeable par LOCAL_LOGIN_ENABLED (/data/.env, break-glass), et
    # ignoré tant qu'aucun utilisateur n'existe (wizard/premier login).
    local_enabled = await _local_login_enabled(request)
    if count == 0:
        local_enabled = True
    return AuthMethodsOut(
        local=local_enabled,
        oidc=oidc_cfg is not None,
        needs_setup=count == 0,
    )


@router.post("/login", response_model=AuthUser)
async def login(body: LoginRequest, request: Request, response: Response) -> AuthUser:
    pool = request.app.state.pool
    settings = request.app.state.settings

    async with pool.acquire() as conn:
        count = await setup_service.user_count(conn)
        if count == 0:
            raise HTTPException(status_code=503, detail="SetupRequired")
        if not await _local_login_enabled(request):
            # Mode OIDC-only (page de configuration OIDC, ou surcharge .env).
            raise HTTPException(status_code=403, detail="connexion locale désactivée")
        row = await conn.fetchrow(_SELECT_FOR_LOGIN, body.email)

    _invalid = HTTPException(status_code=401, detail="identifiants invalides")

    if row is None or row["password_hash"] is None or row["disabled"]:
        # Hachage factice pour uniformiser le temps de réponse avec le cas
        # « email connu » et éviter un oracle d'énumération par timing.
        verify_password(body.password, DUMMY_PASSWORD_HASH)
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
    # Session serveur opaque + cookie HttpOnly (remplace le JWT HS256). Rotation
    # de l'identifiant à chaque login = protection anti-fixation de session.
    async with pool.acquire() as conn:
        await set_session_cookie(
            response,
            conn,
            user.id,
            secure=settings.session_cookie_secure,
            max_age=settings.session_idle_ttl_seconds,
        )
    await pool.execute("UPDATE app_user SET last_login_at = now() WHERE id = $1", user.id)
    return user


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    """Déconnexion : révoque la session EN BASE (pas seulement le cookie retiré),
    puis efface le cookie. Idempotent — un cookie déjà invalide est simplement
    effacé. C'est ce qui fait qu'un jeton copié avant cesse de valoir."""
    token = request.cookies.get(session_cookie_name())
    if token:
        pool = request.app.state.pool
        async with pool.acquire() as conn:
            await revoke_session(conn, token)
    delete_session_cookie(response, secure=request.app.state.settings.session_cookie_secure)


@router.get("/me", response_model=AuthUser)
async def me(user: AuthUser = Depends(require_authenticated)) -> AuthUser:
    return user

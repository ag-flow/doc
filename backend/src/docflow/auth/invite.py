"""Invitation par lien à usage unique (écart n°7 — pas d'envoi d'e-mail).

L'admin crée l'invitation et reçoit une URL qu'il transmet lui-même. Le jeton
est aléatoire (32 octets), stocké UNIQUEMENT haché (sha256), à usage unique et
expirant sous 7 jours. L'invité définit son mot de passe sur `/invite/<token>`.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from docflow.auth.deps import require_superadmin
from docflow.auth.password import hash_password
from docflow.schemas.auth import AuthUser

router = APIRouter(tags=["auth"])
_SuperAdmin = Depends(require_superadmin)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,100}$")
_EXPIRY = "7 days"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class InviteCreate(BaseModel):
    model_config = {"extra": "forbid"}

    email: str
    label: str
    is_admin: bool = False

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("email invalide")
        return v

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("label requis")
        return v


class InviteCreated(BaseModel):
    user_id: uuid.UUID
    email: str
    # Chemin à copier — le jeton n'apparaît qu'ICI, une seule fois.
    invite_path: str
    expires_at: datetime


class InviteInfo(BaseModel):
    email: str
    label: str


class InviteAccept(BaseModel):
    model_config = {"extra": "forbid"}

    password: str

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("mot de passe : 12 caractères minimum")
        return v


@router.post("/admin/users/invite", response_model=InviteCreated, status_code=201)
async def create_invitation(
    body: InviteCreate, request: Request, _: AuthUser = _SuperAdmin
) -> InviteCreated:
    pool: asyncpg.Pool = request.app.state.pool
    token = secrets.token_urlsafe(32)
    async with pool.acquire() as conn, conn.transaction():
        try:
            user_id = await conn.fetchval(
                "INSERT INTO app_user (email, label, is_admin, validated, disabled, source) "
                "VALUES ($1, $2, $3, true, false, 'local') RETURNING id",
                body.email,
                body.label,
                body.is_admin,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(409, "un compte existe déjà avec cet email") from exc
        row = await conn.fetchrow(
            "INSERT INTO user_invitation (user_id, token_hash, expires_at) "
            f"VALUES ($1, $2, now() + interval '{_EXPIRY}') RETURNING expires_at",
            user_id,
            _hash(token),
        )
    assert row is not None
    return InviteCreated(
        user_id=user_id,
        email=body.email,
        invite_path=f"/invite/{token}",
        expires_at=row["expires_at"],
    )


def _check_token(token: str) -> str:
    if not _TOKEN_RE.match(token):
        raise HTTPException(404, "invitation introuvable ou expirée")
    return token


_SELECT_VALID = """
SELECT i.id, i.user_id, u.email, u.label
FROM user_invitation i
JOIN app_user u ON u.id = i.user_id
WHERE i.token_hash = $1 AND i.used_at IS NULL AND i.expires_at > now()
  AND u.disabled = false
"""


@router.get("/invite/{token}", response_model=InviteInfo)
async def get_invitation(token: str, request: Request) -> InviteInfo:
    """Public : qui est invité — le même 404 couvre inconnu, utilisé et expiré."""
    _check_token(token)
    row = await request.app.state.pool.fetchrow(_SELECT_VALID, _hash(token))
    if row is None:
        raise HTTPException(404, "invitation introuvable ou expirée")
    return InviteInfo(email=row["email"], label=row["label"])


@router.post("/invite/{token}", status_code=204)
async def accept_invitation(token: str, body: InviteAccept, request: Request) -> None:
    """Public : définit le mot de passe et consomme le jeton (usage unique)."""
    _check_token(token)
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(_SELECT_VALID + " FOR UPDATE OF i", _hash(token))
        if row is None:
            raise HTTPException(404, "invitation introuvable ou expirée")
        await conn.execute(
            "UPDATE app_user SET password_hash = $1, updated_at = now() WHERE id = $2",
            hash_password(body.password),
            row["user_id"],
        )
        await conn.execute(
            "UPDATE user_invitation SET used_at = now() WHERE id = $1", row["id"]
        )

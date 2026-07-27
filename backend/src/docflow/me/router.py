"""Profil de l'utilisateur connecté (« Mon profil »).

- email : clé de rattachement du compte à la connexion OIDC (la liaison au
  callback exige toujours un email VÉRIFIÉ par l'IdP — oidc/service.py).
- identity : GUID d'identité OBO (contrat v6, GUID-only) — le MÊME GUID que
  dans le profil portail ; `x-portal-actor` est mappé dessus (mcp/obo.py).
"""

from __future__ import annotations

import re
import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from docflow.auth.deps import require_authenticated
from docflow.schemas.auth import AuthUser

router = APIRouter(tags=["me"])
_Auth = Depends(require_authenticated)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MeProfileOut(BaseModel):
    id: uuid.UUID
    email: str
    username: str | None
    label: str
    source: str
    is_admin: bool
    # GUID d'identité OBO (null = non propagé, fail-safe).
    identity: str | None


class MeProfileUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    email: str | None = None
    # GUID d'identité ; chaîne vide = effacer (plus de propagation).
    identity: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("email invalide")
        return v

    @field_validator("identity")
    @classmethod
    def _identity(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if v == "":
            return ""  # sentinelle : effacer
        try:
            return str(uuid.UUID(v))  # forme canonique
        except ValueError as exc:
            raise ValueError("identity doit être un GUID (UUID)") from exc


_SELECT = """
SELECT id, email, username, label, source, is_admin, identity
FROM app_user WHERE id = $1
"""


def _row_to_out(row: asyncpg.Record) -> MeProfileOut:
    return MeProfileOut(**dict(row))


@router.get("/me/profile", response_model=MeProfileOut)
async def get_my_profile(request: Request, user: AuthUser = _Auth) -> MeProfileOut:
    row = await request.app.state.pool.fetchrow(_SELECT, user.id)
    if row is None:
        raise HTTPException(404, "profil introuvable")
    return _row_to_out(row)


@router.patch("/me/profile", response_model=MeProfileOut)
async def update_my_profile(
    body: MeProfileUpdate, request: Request, user: AuthUser = _Auth
) -> MeProfileOut:
    pool = request.app.state.pool
    raw = body.model_dump(exclude_unset=True)
    async with pool.acquire() as conn, conn.transaction():
        if "email" in raw and raw["email"] is not None:
            try:
                await conn.execute(
                    "UPDATE app_user SET email = $1, updated_at = now() WHERE id = $2",
                    raw["email"],
                    user.id,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(409, "cet email est déjà utilisé") from exc
        if "identity" in raw and raw["identity"] is not None:
            value = raw["identity"] or None  # "" → NULL (effacer)
            try:
                await conn.execute(
                    "UPDATE app_user SET identity = $1, updated_at = now() WHERE id = $2",
                    value,
                    user.id,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(409, "ce GUID d'identité est déjà utilisé") from exc
        row = await conn.fetchrow(_SELECT, user.id)
    if row is None:
        raise HTTPException(404, "profil introuvable")
    return _row_to_out(row)

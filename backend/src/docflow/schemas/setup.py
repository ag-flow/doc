from __future__ import annotations

import re

from pydantic import BaseModel, field_validator

_SLUG_RE = re.compile(r"^[a-zA-Z0-9_.\-]{2,50}$")


class SetupStatusOut(BaseModel):
    needs_setup: bool


class InitAdminRequest(BaseModel):
    model_config = {"extra": "forbid"}

    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def username_format(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("username : 2-50 caractères alphanumériques, _, ., -")
        return v

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str) -> str:
        if "@" not in v or len(v) < 3:
            raise ValueError("email invalide")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("mot de passe : 8 caractères minimum")
        return v


class AuthMethodsOut(BaseModel):
    local: bool
    oidc: bool
    needs_setup: bool

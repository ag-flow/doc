from __future__ import annotations

import uuid

from pydantic import BaseModel


class LoginRequest(BaseModel):
    model_config = {"extra": "forbid"}

    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthUser(BaseModel):
    id: uuid.UUID
    email: str
    label: str
    is_admin: bool
    validated: bool
    disabled: bool

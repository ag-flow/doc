from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AdminUserCreate(BaseModel):
    model_config = {"extra": "forbid"}

    email: str
    label: str
    password: str
    is_admin: bool = False


class AdminUserUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    email: str | None = None
    label: str | None = None
    is_admin: bool | None = None
    validated: bool | None = None
    disabled: bool | None = None


class AdminUserSetPassword(BaseModel):
    model_config = {"extra": "forbid"}

    password: str


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    label: str
    username: str | None
    source: str
    is_admin: bool
    validated: bool
    disabled: bool
    has_local_password: bool
    created_at: datetime
    updated_at: datetime

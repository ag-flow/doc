from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VaultWalletCreate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str
    api_key: str


class VaultWalletOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class VaultSecretCreate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    value: str = Field(min_length=1)


class VaultSecretOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    created_at: datetime
    updated_at: datetime

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ApiProfileCreate(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None


class ApiProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    scope_count: int
    key_count: int


class ApiProfileScopeIn(BaseModel):
    model_config = {"extra": "forbid"}
    workspace_slug: str
    block_slug: str | None = None
    read_only: bool = True


class ApiProfileScopeOut(BaseModel):
    id: uuid.UUID
    workspace_slug: str
    block_slug: str | None
    read_only: bool


class ApiProfileDetail(ApiProfileOut):
    scopes: list[ApiProfileScopeOut]


class ScopesUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    scopes: list[ApiProfileScopeIn]


class ApiKeyCreate(BaseModel):
    model_config = {"extra": "forbid"}
    profile_id: uuid.UUID
    label: str = Field(min_length=1, max_length=120)


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    profile_name: str
    label: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool


class ApiKeyCreated(ApiKeyOut):
    key: str

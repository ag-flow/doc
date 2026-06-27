from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from docflow.db.helpers import validate_slug


class WorkspaceCreate(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str
    description: str | None = None

    @field_validator("slug")
    @classmethod
    def _slug_valid(cls, v: str) -> str:
        return validate_slug(v, "slug")


class WorkspaceUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = None
    description: str | None = None


class WorkspaceOut(BaseModel):
    workspace_technical_key: uuid.UUID
    slug: str
    label: str
    description: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

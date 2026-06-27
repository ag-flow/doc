from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from docflow.db.helpers import validate_slug


class DataBlockCreate(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str
    functional_type_slug: str
    parent_slug: str | None = None

    @field_validator("slug")
    @classmethod
    def _slug_valid(cls, v: str) -> str:
        return validate_slug(v, "slug")


class DataBlockUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = None
    parent_slug: str | None = None


class DataBlockOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    functional_type_slug: str
    parent_slug: str | None
    workspace_slug: str
    exposed: bool
    created_at: datetime
    updated_at: datetime

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from docflow.db.helpers import validate_slug

PropType = Literal["text", "int", "restricted_list", "date", "bool", "url", "float", "reference"]


class PropertiesDefCreate(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str
    type: PropType
    default_value: str | None = None
    required: bool = False
    target_functional_type_slug: str | None = None  # uniquement pour type='reference'

    @field_validator("slug")
    @classmethod
    def _slug_valid(cls, v: str) -> str:
        return validate_slug(v, "slug")


class PropertiesDefUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = None
    default_value: str | None = None
    required: bool | None = None


class PropertiesDefOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    type: str
    default_value: str | None
    required: bool
    target_functional_type_slug: str | None = None
    created_at: datetime
    updated_at: datetime


class AllowedValueCreate(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str
    position: int = 0
    color: str | None = None

    @field_validator("slug")
    @classmethod
    def _slug_valid(cls, v: str) -> str:
        return validate_slug(v, "slug")


class AllowedValueUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = None
    position: int | None = None
    color: str | None = None


class AllowedValueOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    position: int
    color: str | None
    created_at: datetime

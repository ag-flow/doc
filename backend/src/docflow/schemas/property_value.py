from __future__ import annotations

from pydantic import BaseModel


class PropertyValueSet(BaseModel):
    model_config = {"extra": "forbid"}

    value: str | None = None
    allowed_value_slug: str | None = None


class PropertyValueOut(BaseModel):
    prop_slug: str
    prop_label: str
    type: str
    value: str | None
    allowed_value_slug: str | None
    allowed_value_label: str | None
    required: bool

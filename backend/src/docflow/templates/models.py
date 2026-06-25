from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConstraintDef(BaseModel):
    model_config = {"extra": "forbid"}

    kind: str
    value: str
    message: str | None = None


class AllowedValueDef(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str
    position: int = 0
    color: str | None = None


class PropDef(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str
    type: Literal["text", "int", "restricted_list"]
    required: bool = False
    default: str | None = None
    constraints: list[ConstraintDef] = Field(default_factory=list)
    allowed_values: list[AllowedValueDef] = Field(default_factory=list)


class TypeDef(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str | None = None
    abstract: bool = False
    inherit: str | None = None
    parent: str | None = None
    properties: list[PropDef] = Field(default_factory=list)


class Template(BaseModel):
    model_config = {"extra": "forbid"}

    version: int
    template: str
    label: str
    functional_types: list[TypeDef]


# ── Resolved (post-inheritance, concrete only) ─────────────────────────────

class ResolvedType(BaseModel):
    """Type concret après résolution de l'héritage — prêt pour le diff/import."""

    slug: str
    label: str
    parent: str | None
    properties: list[PropDef]

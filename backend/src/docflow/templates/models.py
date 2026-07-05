from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    type: Literal["text", "int", "restricted_list", "date", "bool", "url", "float", "reference"]
    required: bool = False
    default: str | None = None
    # Comportement serveur (réservé au type 'date') : auto_now = date courante
    # à chaque enregistrement du document ; auto_now_create = à la création.
    behavior: Literal["auto_now", "auto_now_create"] | None = None
    constraints: list[ConstraintDef] = Field(default_factory=list)
    allowed_values: list[AllowedValueDef] = Field(default_factory=list)
    # reference-type fields (spec MREL)
    target_type: str | None = None
    max_occurrences: int | None = None

    @model_validator(mode="after")
    def _behavior_date_only(self) -> PropDef:
        if self.behavior is not None and self.type != "date":
            raise ValueError("behavior est réservé aux propriétés de type 'date'")
        return self


class TypeDef(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str | None = None
    abstract: bool = False
    inherit: str | None = None
    parent: str | None = None
    properties: list[PropDef] = Field(default_factory=list)
    content_template: str | None = None  # spec MEXP


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

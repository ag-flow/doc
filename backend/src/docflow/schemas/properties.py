from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

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
    # Comportement serveur (réservé au type 'date') : auto_now = date courante
    # à chaque enregistrement du document ; auto_now_create = à la création.
    # Une propriété à behavior est refusée en écriture manuelle.
    behavior: Literal["auto_now", "auto_now_create"] | None = None

    @field_validator("slug")
    @classmethod
    def _slug_valid(cls, v: str) -> str:
        return validate_slug(v, "slug")

    @model_validator(mode="after")
    def _behavior_date_only(self) -> PropertiesDefCreate:
        if self.behavior is not None and self.type != "date":
            raise ValueError("behavior est réservé aux propriétés de type 'date'")
        return self


class PropertiesDefUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = None
    default_value: str | None = None
    required: bool | None = None
    # Changement de type : libre sans donnée existante ; avec des valeurs en
    # base, seules les transitions cohérentes sont permises (service). Le slug,
    # lui, est IMMUABLE — il n'existe pas dans ce schéma.
    type: PropType | None = None
    # None explicite = retirer le comportement (distingué de « absent »).
    behavior: Literal["auto_now", "auto_now_create"] | None = None


class PropertiesDefOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    type: str
    default_value: str | None
    required: bool
    target_functional_type_slug: str | None = None
    behavior: str | None = None
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

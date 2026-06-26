from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

VALID_EVENTS: frozenset[str] = frozenset(
    {"document.created", "document.updated", "document.deleted"}
)


class WebhookCreate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str
    url: str
    headers: dict[str, str] = {}
    events: list[str] = []
    active: bool = True

    @field_validator("label")
    @classmethod
    def label_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("label ne peut pas être vide")
        return v

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("url ne peut pas être vide")
        return v

    @field_validator("events")
    @classmethod
    def events_valid(cls, v: list[str]) -> list[str]:
        invalid = set(v) - VALID_EVENTS
        if invalid:
            raise ValueError(f"événements invalides : {sorted(invalid)}")
        return list(set(v))  # dédoublonnage


class WebhookUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    events: list[str] | None = None
    active: bool | None = None

    @field_validator("events")
    @classmethod
    def events_valid(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        invalid = set(v) - VALID_EVENTS
        if invalid:
            raise ValueError(f"événements invalides : {sorted(invalid)}")
        return list(set(v))


class WebhookOut(BaseModel):
    id: uuid.UUID
    workspace_technical_key: uuid.UUID
    label: str
    url: str
    headers: dict[str, str]  # déchiffrés à la lecture par l'admin
    events: list[str]
    active: bool
    created_at: datetime
    updated_at: datetime


class WebhookTestOut(BaseModel):
    status_code: int | None
    error: str | None

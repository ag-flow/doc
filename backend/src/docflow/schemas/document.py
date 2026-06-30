from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")


class DocumentCreate(BaseModel):
    model_config = {"extra": "forbid"}

    title: str
    block_id: uuid.UUID
    slug: str
    content: str | None = None
    parent_id: uuid.UUID | None = None
    functional_type_slug: str | None = None

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug invalide : minuscules, chiffres et tirets, 2–80 chars, "
                "commence et finit par un alphanumérique"
            )
        return v


class DocumentCreateInBlock(BaseModel):
    model_config = {"extra": "forbid"}

    title: str
    slug: str
    parent_id: uuid.UUID | None = None
    functional_type_slug: str | None = None

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug invalide : minuscules, chiffres et tirets, 2–80 chars, "
                "commence et finit par un alphanumérique"
            )
        return v


class DocumentUpdate(BaseModel):
    """Mise à jour partielle.

    title / content → bump versionné (expected_version obligatoire si l'un des deux est fourni).
    parent_id / functional_type_slug / slug → mise à jour directe, sans versioning.
    """

    model_config = {"extra": "forbid"}

    title: str | None = None
    content: str | None = None
    expected_version: int | None = None
    parent_id: uuid.UUID | None = None
    functional_type_slug: str | None = None
    slug: str | None = None

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: str | None) -> str | None:
        if v is not None and not _SLUG_RE.match(v):
            raise ValueError(
                "slug invalide : minuscules, chiffres et tirets, 2–80 chars, "
                "commence et finit par un alphanumérique"
            )
        return v


class DocumentOut(BaseModel):
    doc_technical_key: uuid.UUID
    title: str
    type: str
    slug: str | None
    content: str | None
    version: int
    parent_id: uuid.UUID | None
    functional_type_slug: str | None
    workspace_slug: str
    data_block_ref: uuid.UUID
    exposed: bool
    created_at: datetime
    updated_at: datetime

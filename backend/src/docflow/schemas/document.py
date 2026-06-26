from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    model_config = {"extra": "forbid"}

    title: str
    content: str | None = None
    parent_id: uuid.UUID | None = None
    functional_type_slug: str | None = None


class DocumentUpdate(BaseModel):
    """Mise à jour partielle.

    title / content → bump versionné (expected_version obligatoire si l'un des deux est fourni).
    parent_id / functional_type_slug → mise à jour directe, sans versioning.
    """

    model_config = {"extra": "forbid"}

    title: str | None = None
    content: str | None = None
    expected_version: int | None = None
    parent_id: uuid.UUID | None = None
    functional_type_slug: str | None = None


class DocumentOut(BaseModel):
    doc_technical_key: uuid.UUID
    title: str
    type: str
    content: str | None
    version: int
    parent_id: uuid.UUID | None
    functional_type_slug: str | None
    workspace_slug: str
    created_at: datetime
    updated_at: datetime

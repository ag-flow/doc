from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    model_config = {"extra": "forbid"}

    title: str
    contenu: str | None = None
    parent_id: uuid.UUID | None = None
    functional_type_slug: str | None = None


class DocumentUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    title: str | None = None
    contenu: str | None = None
    parent_id: uuid.UUID | None = None
    functional_type_slug: str | None = None


class DocumentOut(BaseModel):
    doc_technical_key: uuid.UUID
    title: str
    type: str
    contenu: str | None
    parent_id: uuid.UUID | None
    functional_type_slug: str | None
    workspace_slug: str
    created_at: datetime
    updated_at: datetime

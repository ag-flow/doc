from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ArtifactCreatedOut(BaseModel):
    """Réponse à l'upload d'un artefact (créé ou dédupliqué)."""

    id: uuid.UUID
    url: str
    deduplicated: bool
    filename: str
    extension: str
    media_type: str
    size_bytes: int
    sha256: str
    crc32: int


class ArtifactMetaOut(BaseModel):
    """Métadonnées d'un artefact (sans le binaire)."""

    id: uuid.UUID
    filename: str
    extension: str
    media_type: str
    size_bytes: int
    sha256: str
    crc32: int
    refcount: int
    created_at: datetime

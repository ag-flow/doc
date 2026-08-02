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


class ArtifactTypeOut(BaseModel):
    """Une entrée du registre des types d'artefact acceptés."""

    extension: str
    media_type: str
    label: str
    created_at: datetime
    updated_at: datetime


class ArtifactTypeCreate(BaseModel):
    model_config = {"extra": "forbid"}

    extension: str
    media_type: str
    label: str = ""


class ArtifactTypeUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    media_type: str
    label: str = ""


class ArtifactSummaryOut(BaseModel):
    """Un artefact dans une liste : toutes les colonnes sauf le binaire, + refcount."""

    id: uuid.UUID
    filename: str
    extension: str
    media_type: str
    size_bytes: int
    sha256: str
    crc32: int
    created_by: uuid.UUID | None
    created_at: datetime
    refcount: int


class ArtifactListOut(BaseModel):
    """Réponse paginée de la liste/recherche d'artefacts."""

    items: list[ArtifactSummaryOut]
    total: int
    limit: int
    offset: int

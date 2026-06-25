from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class OidcConfigSet(BaseModel):
    """Corps de la requête PUT /admin/oidc — le secret_ref est une référence vault."""

    model_config = {"extra": "forbid"}

    issuer: str
    client_id: str
    client_secret_ref: str
    enabled: bool = False


class OidcConfigOut(BaseModel):
    """Réponse GET /admin/oidc — le client_secret_ref est MASQUÉ."""

    id: uuid.UUID
    issuer: str
    client_id: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class OidcPublicConfig(BaseModel):
    """Config minimale exposée publiquement pour le frontend."""

    issuer: str
    client_id: str
    enabled: bool

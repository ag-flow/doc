from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
    """Config minimale exposée publiquement pour le frontend.

    `authorization_endpoint` n'est renseigné que par GET /auth/oidc/config
    (découverte serveur) — jamais stocké en base.
    """

    issuer: str
    client_id: str
    enabled: bool
    authorization_endpoint: str | None = None


class OidcCallbackIn(BaseModel):
    """Corps de POST /auth/oidc/callback — flow authorization-code.

    Le backend échange lui-même le `code` au token endpoint de l'issuer
    configuré puis vérifie l'id_token (signature JWKS, iss, aud, exp, nonce).
    Aucun claim posté par le client n'est accepté tel quel (AUTH-01).
    """

    model_config = {"extra": "forbid"}

    code: str = Field(min_length=1, max_length=4096)
    redirect_uri: str = Field(min_length=1, max_length=2048)
    # Nonce généré par le client au départ du flow, pour lier l'id_token à sa session.
    nonce: str | None = Field(default=None, max_length=512)

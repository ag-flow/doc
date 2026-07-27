from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ContractImport(BaseModel):
    model_config = {"extra": "forbid"}

    label: str
    source_url: str | None = None
    raw_spec: dict[str, object]


class ContractUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = None


class ContractOut(BaseModel):
    id: uuid.UUID
    label: str
    source_url: str | None
    version: str | None
    imported_at: datetime
    updated_at: datetime


class AuthHeaderRequirement(BaseModel):
    """En-tête d'authentification requis par un schéma de sécurité du contrat."""

    header: str          # nom du header (ex. Authorization, X-API-Key)
    value_prefix: str    # préfixe de valeur (ex. "Bearer ", "" pour apiKey)
    scheme_name: str     # clé du securityScheme (pour affichage)
    scheme_type: str     # http | apiKey


class OperationOut(BaseModel):
    operation_id: str | None
    method: str
    path: str
    summary: str | None
    parameters: list[dict[str, object]]
    request_body: dict[str, object] | None
    body_skeleton: dict[str, object] | None
    # Headers d'auth déduits de la sécurité (op-level, sinon racine).
    auth_headers: list[AuthHeaderRequirement] = []


class ContractDetailOut(BaseModel):
    contract: ContractOut
    operations: list[OperationOut]
    # URLs de serveur déclarées par le contrat (spec.servers[].url) — servent à
    # construire l'URL d'appel (server + path) à la sélection de l'opération.
    servers: list[str] = []

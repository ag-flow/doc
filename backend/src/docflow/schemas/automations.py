from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class AutomationHeaderIn(BaseModel):
    model_config = {"extra": "forbid"}

    name: str
    value: str | None = None
    secret_ref: str | None = None
    # Préfixe de la valeur finale (ex. "Bearer " pour un schéma HTTP bearer).
    value_prefix: str | None = None
    required: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def xor_value_secret(self) -> AutomationHeaderIn:
        if self.value is not None and self.secret_ref is not None:
            raise ValueError("value et secret_ref sont mutuellement exclusifs")
        return self


class AutomationHeaderOut(BaseModel):
    id: uuid.UUID
    name: str
    value: str | None
    secret_ref: str | None
    value_prefix: str | None
    required: bool
    enabled: bool


class AutomationCreate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str
    # Toujours créé DÉSACTIVÉ (activation via le toggle de la carte).
    active: bool = False
    # Workspaces couverts (l'automate est visible et se déclenche dans chacun).
    # Vide à la création = [workspace courant]. Jamais vide en base.
    workspace_slugs: list[str] = []
    # eventCodes déclencheurs (les 6 codes du catalogue docflow.document.*).
    event_codes: list[str] = []
    # Filtres additionnels (AND) : blocs et/ou types de document (vide = tous).
    block_slugs: list[str] = []
    functional_type_slugs: list[str] = []
    # Rétro-compat : anciennes cases C/U (backfillées vers event_codes en base).
    on_create: bool = False
    on_update: bool = False
    delay_minutes: int = 0
    contract_ref: uuid.UUID | None = None
    operation_id: str | None = None
    url: str
    http_method: str
    body_template: str | None = None
    headers: list[AutomationHeaderIn] = []


class AutomationUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = None
    active: bool | None = None
    workspace_slugs: list[str] | None = None
    event_codes: list[str] | None = None
    block_slugs: list[str] | None = None
    functional_type_slugs: list[str] | None = None
    on_create: bool | None = None
    on_update: bool | None = None
    delay_minutes: int | None = None
    contract_ref: uuid.UUID | None = None
    operation_id: str | None = None
    url: str | None = None
    http_method: str | None = None
    body_template: str | None = None
    headers: list[AutomationHeaderIn] | None = None


class AutomationOut(BaseModel):
    id: uuid.UUID
    workspace_technical_key: uuid.UUID
    label: str
    active: bool
    # Events déclencheurs au-delà du curseur, pas encore évalués (0 = à jour).
    pending_count: int = 0
    # Position d'évaluation DANS LE WORKSPACE demandé (1..n).
    position: int = 0
    workspace_slugs: list[str] = []
    event_codes: list[str]
    block_slugs: list[str] = []
    functional_type_slugs: list[str] = []
    on_create: bool
    on_update: bool
    delay_minutes: int
    contract_ref: uuid.UUID | None
    operation_id: str | None
    url: str
    http_method: str
    body_template: str | None
    headers: list[AutomationHeaderOut]
    created_at: datetime
    updated_at: datetime


class AutomationRunOut(BaseModel):
    id: uuid.UUID
    automation_ref: uuid.UUID
    document_ref: uuid.UUID | None
    document_version: int | None
    change_log_seq: int
    status: str
    executed_at: datetime
    # Détails de l'appel (historique enrichi).
    http_status: int | None = None
    url: str | None = None
    request_body: str | None = None    # corps envoyé, variables résolues
    response_body: str | None = None   # corps/message de réponse
    event_code: str | None = None
    manual: bool = False               # déclenché via « jouer l'event » (test)


class AutomationOrderIn(BaseModel):
    """Réordonnancement des automates d'un workspace (drag & drop)."""

    model_config = {"extra": "forbid"}

    # Ids dans le nouvel ordre — doit couvrir EXACTEMENT les automates du workspace.
    ids: list[uuid.UUID]

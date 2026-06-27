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


class OperationOut(BaseModel):
    operation_id: str | None
    method: str
    path: str
    summary: str | None
    parameters: list[dict[str, object]]
    request_body: dict[str, object] | None
    body_skeleton: dict[str, object] | None


class ContractDetailOut(BaseModel):
    contract: ContractOut
    operations: list[OperationOut]

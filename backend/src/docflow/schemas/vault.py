from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class VaultWalletCreate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str
    api_key: str


class VaultWalletOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

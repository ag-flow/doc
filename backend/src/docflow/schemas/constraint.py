from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ConstraintKind = Literal["min", "max", "min_length", "max_length", "pattern"]


class ConstraintCreate(BaseModel):
    model_config = {"extra": "forbid"}

    kind: ConstraintKind
    value: str
    message: str | None = None


class ConstraintOut(BaseModel):
    id: uuid.UUID
    kind: str
    value: str
    message: str | None
    created_at: datetime

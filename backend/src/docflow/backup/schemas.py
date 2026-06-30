from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")


class BackupJobCreate(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str = Field(min_length=1, max_length=120)
    strategy: Literal["db_dump", "git_sync"]
    enabled: bool = True
    remote_point_slug: str

    # Périmètre — None = toute l'instance (git_sync uniquement)
    workspace_slug: str | None = None

    # Planification : exactement un des deux
    schedule_cron: str | None = None
    schedule_every_seconds: int | None = Field(default=None, gt=0)

    # Paramètre git_sync
    git_base_path: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> BackupJobCreate:
        if not _SLUG_RE.match(self.slug):
            raise ValueError("slug : minuscules, chiffres, tirets, 2-80 chars")
        has_cron = self.schedule_cron is not None
        has_interval = self.schedule_every_seconds is not None
        if has_cron == has_interval:
            raise ValueError("exactement un de schedule_cron ou schedule_every_seconds est requis")
        return self


class BackupJobUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str = Field(min_length=1, max_length=120)
    enabled: bool
    remote_point_slug: str
    workspace_slug: str | None = None
    schedule_cron: str | None = None
    schedule_every_seconds: int | None = Field(default=None, gt=0)
    git_base_path: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> BackupJobUpdate:
        has_cron = self.schedule_cron is not None
        has_interval = self.schedule_every_seconds is not None
        if has_cron == has_interval:
            raise ValueError("exactement un de schedule_cron ou schedule_every_seconds est requis")
        return self


class BackupJobOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    strategy: str
    enabled: bool
    remote_point_slug: str
    workspace_slug: str | None
    schedule_cron: str | None
    schedule_every_seconds: int | None
    git_base_path: str | None
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None
    last_run_status: str | None


class BackupJobRunOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    status: str
    error_message: str | None
    last_change_seq: int | None
    files_written: int | None
    files_deleted: int | None
    commit_sha: str | None

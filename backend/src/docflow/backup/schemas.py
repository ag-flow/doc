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
    # Sous-périmètre optionnel : un bloc (+ sa descendance) du workspace
    # ci-dessus (git_sync uniquement). Requiert workspace_slug : un bloc
    # appartient toujours à un workspace précis.
    data_block_slug: str | None = None

    # Planification : exactement un des deux
    schedule_cron: str | None = None
    schedule_every_seconds: int | None = Field(default=None, gt=0)

    # Paramètre git_sync
    git_base_path: str | None = None
    # Dump uniquement : dépose aussi docflow_restore.env (clé de chiffrement,
    # JWT_SECRET, DATABASE_URL) dans le répertoire de destination.
    include_restore_env: bool = False
    # Dump uniquement : nombre d'archives à conserver sur le remote
    # (les plus anciennes au-delà sont purgées, .key compris). None = tout garder.
    retention_count: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate(self) -> BackupJobCreate:
        if not _SLUG_RE.match(self.slug):
            raise ValueError("slug : minuscules, chiffres, tirets, 2-80 chars")
        has_cron = self.schedule_cron is not None
        has_interval = self.schedule_every_seconds is not None
        if has_cron == has_interval:
            raise ValueError("exactement un de schedule_cron ou schedule_every_seconds est requis")
        if self.data_block_slug is not None and self.workspace_slug is None:
            raise ValueError("data_block_slug requiert workspace_slug")
        return self


class BackupJobUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    label: str = Field(min_length=1, max_length=120)
    enabled: bool
    remote_point_slug: str
    workspace_slug: str | None = None
    data_block_slug: str | None = None
    schedule_cron: str | None = None
    schedule_every_seconds: int | None = Field(default=None, gt=0)
    git_base_path: str | None = None
    include_restore_env: bool = False
    retention_count: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate(self) -> BackupJobUpdate:
        has_cron = self.schedule_cron is not None
        has_interval = self.schedule_every_seconds is not None
        if has_cron == has_interval:
            raise ValueError("exactement un de schedule_cron ou schedule_every_seconds est requis")
        if self.data_block_slug is not None and self.workspace_slug is None:
            raise ValueError("data_block_slug requiert workspace_slug")
        return self


class BackupJobOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    strategy: str
    enabled: bool
    remote_point_slug: str
    workspace_slug: str | None
    data_block_slug: str | None
    schedule_cron: str | None
    schedule_every_seconds: int | None
    git_base_path: str | None
    include_restore_env: bool = False
    retention_count: int | None = None
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None
    last_run_status: str | None


class DumpArchiveOut(BaseModel):
    """Une archive de dump présente sur le remote point d'un job db_dump."""

    filename: str
    scope: str
    job_id: str
    created_at: datetime
    size: int | None = None


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

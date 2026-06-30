from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")


def _valid_slug(v: str) -> str:
    if not _SLUG_RE.match(v):
        raise ValueError("slug : minuscules, chiffres, tirets, 2-80 chars")
    return v


# ── Certificats ──────────────────────────────────────────────────────────────


class RemoteCertificateCreate(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str = Field(min_length=1, max_length=120)
    cert_type: Literal["ssh_key", "tls"]
    public_part: str = Field(min_length=1)
    private_key: str = Field(min_length=1)  # jamais renvoyé — chiffré à l'écriture
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_slug(self) -> RemoteCertificateCreate:
        _valid_slug(self.slug)
        return self


class RemoteCertificateOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    cert_type: str
    public_part: str
    fingerprint: str | None
    expires_at: datetime | None
    created_at: datetime


# ── Remote Points ─────────────────────────────────────────────────────────────

PointType = Literal["ftp", "ftps", "sftp", "git"]
AuthType = Literal["password", "pat", "certificate"]
AuthStorage = Literal["local", "vault"]
GitProvider = Literal["github", "gitlab", "gitea", "custom"]


class RemotePointCreate(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str
    label: str = Field(min_length=1, max_length=120)
    point_type: PointType
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=120)

    # Git uniquement
    git_provider: GitProvider | None = None
    git_repo: str | None = None
    git_branch: str = "main"

    # Auth
    auth_type: AuthType
    auth_storage: AuthStorage | None = None
    auth_secret: str | None = None  # plain — chiffré Fernet à l'écriture
    auth_vault_ref: str | None = None  # ${vault://...}
    certificate_slug: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> RemotePointCreate:
        _valid_slug(self.slug)
        self._check_git()
        self._check_auth()
        return self

    def _check_git(self) -> None:
        if self.point_type == "git":
            if not self.git_provider:
                raise ValueError("git_provider requis pour le type git")
            if not self.git_repo:
                raise ValueError("git_repo requis pour le type git")

    def _check_auth(self) -> None:
        if self.auth_type in ("password", "pat"):
            if not self.auth_storage:
                raise ValueError("auth_storage requis pour password/pat")
            if self.auth_storage == "local" and not self.auth_secret:
                raise ValueError("auth_secret requis quand auth_storage=local")
            if self.auth_storage == "vault" and not self.auth_vault_ref:
                raise ValueError("auth_vault_ref requis quand auth_storage=vault")
        elif self.auth_type == "certificate":
            if not self.certificate_slug:
                raise ValueError("certificate_slug requis pour l'auth par certificat")


class RemotePointUpdate(BaseModel):
    """Remplacement complet — mêmes règles que Create, slug immuable."""

    model_config = {"extra": "forbid"}

    label: str = Field(min_length=1, max_length=120)
    point_type: PointType
    host: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=120)
    git_provider: GitProvider | None = None
    git_repo: str | None = None
    git_branch: str = "main"
    auth_type: AuthType
    auth_storage: AuthStorage | None = None
    auth_secret: str | None = None
    auth_vault_ref: str | None = None
    certificate_slug: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> RemotePointUpdate:
        tmp = RemotePointCreate(
            slug="placeholder",
            label=self.label,
            point_type=self.point_type,
            host=self.host,
            port=self.port,
            username=self.username,
            git_provider=self.git_provider,
            git_repo=self.git_repo,
            git_branch=self.git_branch,
            auth_type=self.auth_type,
            auth_storage=self.auth_storage,
            auth_secret=self.auth_secret,
            auth_vault_ref=self.auth_vault_ref,
            certificate_slug=self.certificate_slug,
        )
        _ = tmp  # validation déléguée à RemotePointCreate
        return self


class RemotePointOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    point_type: str
    host: str
    port: int | None
    username: str
    git_provider: str | None
    git_repo: str | None
    git_branch: str
    auth_type: str
    auth_storage: str | None
    auth_vault_ref: str | None
    certificate_slug: str | None
    has_local_secret: bool  # True si auth_secret_enc IS NOT NULL
    created_at: datetime
    updated_at: datetime

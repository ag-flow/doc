from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from docflow.secrets.secret import Secret


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid", case_sensitive=False)

    database_url: str
    admin_email: str
    admin_password: Secret
    jwt_secret: Secret
    harpocrate_url: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

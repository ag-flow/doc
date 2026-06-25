from __future__ import annotations

import pytest
from pydantic import ValidationError

from docflow.config.settings import Settings
from docflow.secrets.secret import Secret

_BASE_ENV = {
    "DATABASE_URL": "postgresql://localhost/docflow",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_PASSWORD": "s3cr3t",
    "JWT_SECRET": "jwt_key",
}


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)

    s = Settings()

    assert s.database_url == "postgresql://localhost/docflow"
    assert s.admin_email == "admin@example.com"
    assert isinstance(s.admin_password, Secret)
    assert isinstance(s.jwt_secret, Secret)
    assert s.harpocrate_url is None
    assert s.log_level == "INFO"


def test_settings_optional_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("HARPOCRATE_URL", "https://vault.example.com")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    s = Settings()

    assert s.harpocrate_url == "https://vault.example.com"
    assert s.log_level == "DEBUG"


def test_settings_rejects_unknown_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """extra='forbid' must reject unknown fields passed to the constructor."""
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)

    with pytest.raises(ValidationError):
        Settings(**_BASE_ENV, unknown_field="boom")  # type: ignore[call-arg]


def test_settings_missing_required_field(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings()

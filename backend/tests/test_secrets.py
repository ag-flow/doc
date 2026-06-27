from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from docflow.secrets.resolver import resolve
from docflow.secrets.secret import Secret

# ── Secret type ──────────────────────────────────────────────────────────────


def test_secret_repr_does_not_leak() -> None:
    s = Secret("super_secret_value_xyz")
    assert "super_secret_value_xyz" not in repr(s)
    assert "super_secret_value_xyz" not in str(s)


def test_secret_repr_format() -> None:
    s = Secret("anything")
    assert repr(s) == "Secret(***)"
    assert str(s) == "***"


def test_secret_reveal() -> None:
    s = Secret("my_raw_value")
    assert s.reveal() == "my_raw_value"


def test_secret_not_leaked_in_log(capfd: pytest.CaptureFixture[str]) -> None:
    """Logging a Secret must never expose the raw value."""
    import logging

    import structlog

    structlog.configure(
        processors=[structlog.stdlib.add_log_level, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
    logging.basicConfig(format="%(message)s", level=logging.DEBUG)

    raw = "DO_NOT_LOG_THIS_SECRET_VALUE"
    s = Secret(raw)

    log = structlog.get_logger()
    log.info("test_event", secret=s)

    captured = capfd.readouterr()
    assert raw not in captured.out
    assert raw not in captured.err


def test_secret_pydantic_field() -> None:
    """Secret must work as a pydantic-settings field type."""
    from docflow.config.settings import Settings

    s = Settings(
        database_url="postgresql://localhost/test",
        admin_email="a@b.com",
        admin_password="plain",
        jwt_secret="jwt",
    )
    assert isinstance(s.admin_password, Secret)
    assert s.admin_password.reveal() == "plain"
    assert "plain" not in repr(s.admin_password)


# ── Resolver — valeurs inline ─────────────────────────────────────────────────


async def test_resolver_returns_inline_value() -> None:
    s = Secret("plain_inline_value")
    result = await resolve(s, harpocrate_url=None)
    assert result == "plain_inline_value"


async def test_resolver_inline_ignores_harpocrate_url() -> None:
    """Inline value must be returned even when harpocrate_url is provided."""
    s = Secret("inline_value")
    result = await resolve(s, harpocrate_url="https://vault.example.com")
    assert result == "inline_value"


# ── Resolver — erreurs de configuration ──────────────────────────────────────


async def test_resolver_vault_ref_without_harpocrate_raises() -> None:
    s = Secret("${vault://mywallet:/oidc/secret}")
    with pytest.raises(ValueError, match="HARPOCRATE_URL"):
        await resolve(s, harpocrate_url=None)


async def test_resolver_vault_ref_without_pool_raises() -> None:
    s = Secret("${vault://mywallet:/oidc/secret}")
    with pytest.raises(ValueError, match="pool"):
        await resolve(s, harpocrate_url="https://vault.example.com")


async def test_resolver_wallet_not_found_raises() -> None:
    s = Secret("${vault://unknown-wallet:/oidc/secret}")
    mock_pool = MagicMock()

    with patch("docflow.vault.service.get_api_key", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="unknown-wallet"):
            await resolve(
                s,
                harpocrate_url="https://vault.example.com",
                pool=mock_pool,
                enc_key="fakekey",
            )


# ── Resolver — appel Harpocrate ───────────────────────────────────────────────


async def test_resolver_vault_ref_calls_harpocrate() -> None:
    """Un ${vault://...} doit appeler VaultClient.secrets.get et retourner la valeur."""
    s = Secret("${vault://mywallet:/oidc/client_secret}")
    mock_pool = MagicMock()

    mock_secrets = MagicMock()
    mock_secrets.get.return_value = "the_real_client_secret"
    mock_client_instance = MagicMock()
    mock_client_instance.secrets = mock_secrets

    with patch("docflow.vault.service.get_api_key", new=AsyncMock(return_value="hrpv_1_abc")):
        with patch("harpocrate.VaultClient", return_value=mock_client_instance) as mock_cls:
            result = await resolve(
                s,
                harpocrate_url="https://vault.yoops.org",
                pool=mock_pool,
                enc_key="someenckey",
            )

    assert result == "the_real_client_secret"
    mock_cls.assert_called_once_with(token="hrpv_1_abc", base_url="https://vault.yoops.org")
    mock_secrets.get.assert_called_once_with("/oidc/client_secret")


async def test_resolver_vault_ref_passes_correct_path() -> None:
    """Le path est transmis tel quel (avec slash initial) à secrets.get()."""
    s = Secret("${vault://corp:/infra/db/postgres_password}")
    mock_pool = MagicMock()

    mock_secrets = MagicMock()
    mock_secrets.get.return_value = "db_secret"
    mock_client_instance = MagicMock()
    mock_client_instance.secrets = mock_secrets

    with patch("docflow.vault.service.get_api_key", new=AsyncMock(return_value="hrpv_tok")):
        with patch("harpocrate.VaultClient", return_value=mock_client_instance):
            result = await resolve(
                s,
                harpocrate_url="https://vault.example.com",
                pool=mock_pool,
                enc_key="key",
            )

    assert result == "db_secret"
    mock_secrets.get.assert_called_once_with("/infra/db/postgres_password")

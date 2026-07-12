from __future__ import annotations

import types
from collections.abc import AsyncIterator

import asyncpg
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from docflow.remote import service as svc
from docflow.remote.probe import probe_connection
from docflow.remote.schemas import RemotePointCreate
from docflow.secrets.secret import Secret

_FERNET_KEY = Fernet.generate_key().decode()


def _settings() -> object:
    return types.SimpleNamespace(encryption_key=Secret(_FERNET_KEY), harpocrate_url=None)


@pytest.fixture(autouse=True)
async def _clean(db_pool: asyncpg.Pool) -> AsyncIterator[None]:
    yield
    await db_pool.execute("DELETE FROM remote_point")
    await db_pool.execute("DELETE FROM remote_certificate")


async def _make_point(db_pool: asyncpg.Pool, **overrides: object) -> None:
    defaults: dict[str, object] = {
        "slug": "pt-conn",
        "label": "Point de test",
        "point_type": "sftp",
        "host": "sftp.example.com",
        "username": "user",
        "auth_type": "password",
        "auth_storage": "local",
        "auth_secret": "s3cr3t",
    }
    defaults.update(overrides)
    await svc.create_point(db_pool, RemotePointCreate(**defaults), _FERNET_KEY)  # type: ignore[arg-type]


async def test_connection_sftp_success(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _make_point(db_pool)
    calls: dict[str, object] = {}

    def _fake_test_sftp(**kwargs: object) -> None:
        calls.update(kwargs)

    monkeypatch.setattr("docflow.backup.db_dump.test_sftp_connection", _fake_test_sftp)
    result = await probe_connection(db_pool, "pt-conn", _settings())
    assert result == {"ok": True, "detail": "Connexion réussie"}
    assert calls["host"] == "sftp.example.com"
    assert calls["username"] == "user"
    assert calls["password"] == "s3cr3t"
    assert calls["ssh_key_path"] is None


async def test_connection_sftp_failure_reports_detail(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _make_point(db_pool)

    def _fake_test_sftp(**kwargs: object) -> None:
        raise RuntimeError("Authentication failed")

    monkeypatch.setattr("docflow.backup.db_dump.test_sftp_connection", _fake_test_sftp)
    result = await probe_connection(db_pool, "pt-conn", _settings())
    assert result == {"ok": False, "detail": "Authentication failed"}


async def test_connection_ftp_requires_password(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un point ftp/ftps sans secret résolu (cas théorique) échoue proprement, sans se connecter."""
    await _make_point(db_pool, point_type="ftp")

    called = False

    def _fake_test_ftp(**kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("docflow.backup.db_dump.test_ftp_connection", _fake_test_ftp)
    monkeypatch.setattr(
        "docflow.remote.connection.resolve_dump_auth",
        lambda pool, slug, settings: _resolved_no_password(),
    )
    result = await probe_connection(db_pool, "pt-conn", _settings())
    assert result["ok"] is False
    assert "mot de passe" in str(result["detail"])
    assert called is False


async def _resolved_no_password() -> tuple[str, int | None, str, str | None, str | None]:
    return "ftp.example.com", None, "user", None, None


async def test_connection_git_uses_ls_remote(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _make_point(
        db_pool,
        slug="pt-git",
        point_type="git",
        host="github.com",
        auth_type="pat",
        auth_storage="local",
        auth_secret="ghp_token",
        git_provider="github",
        git_repo="org/repo",
    )
    calls: dict[str, object] = {}

    def _fake_test_git(remote_url: str, **kwargs: object) -> None:
        calls["remote_url"] = remote_url
        calls.update(kwargs)

    monkeypatch.setattr("docflow.backup.git_sync.test_git_connection", _fake_test_git)
    result = await probe_connection(db_pool, "pt-git", _settings())
    assert result == {"ok": True, "detail": "Connexion réussie"}
    assert calls["remote_url"] == "https://github.com/org/repo.git"
    assert calls["ssh_key_path"] is None


async def test_connection_git_bitbucket_uses_bitbucket_host(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _make_point(
        db_pool,
        slug="pt-bitbucket",
        point_type="git",
        host="bitbucket.org",
        auth_type="pat",
        auth_storage="local",
        auth_secret="app-password",
        git_provider="bitbucket",
        git_repo="team/repo",
    )
    calls: dict[str, object] = {}

    def _fake_test_git(remote_url: str, **kwargs: object) -> None:
        calls["remote_url"] = remote_url
        calls.update(kwargs)

    monkeypatch.setattr("docflow.backup.git_sync.test_git_connection", _fake_test_git)
    result = await probe_connection(db_pool, "pt-bitbucket", _settings())
    assert result == {"ok": True, "detail": "Connexion réussie"}
    assert calls["remote_url"] == "https://bitbucket.org/team/repo.git"


async def test_connection_unknown_point_raises_404(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await probe_connection(db_pool, "missing", _settings())
    assert exc_info.value.status_code == 404

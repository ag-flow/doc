"""T3 (E2) — Stockage au choix par secret (local / endpoint vault), fail closed.

Un secret est stocké en local (valeur chiffrée) OU dans un endpoint vault (chemin
seul en base). Aucun repli automatique : un endpoint inexistant est refusé (422).
Fabrique create_backend pour la résolution ; HARPOCRATE_API_KEY reste local.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.schemas.vault import VaultSecretCreate, VaultWalletCreate
from docflow.secrets.backends import HarpocrateBackend, LocalBackend, create_backend
from docflow.vault import service as vault_svc

_ENC = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


async def _owner(pool: asyncpg.Pool, email: str) -> asyncpg.Record:
    return await pool.fetchval(
        "INSERT INTO app_user (email, label, source, validated, is_admin) "
        "VALUES ($1, 'T', 'local', true, true) RETURNING id",
        email,
    )


async def _endpoint(pool: asyncpg.Pool, owner: asyncpg.Record, name: str):
    key = await vault_svc.create_secret(
        pool,
        owner,
        VaultSecretCreate(
            label="K", slug=f"k-{name}", value="hrpv_1_tok", secret_type="HARPOCRATE_API_KEY"
        ),
        enc_key=_ENC,
    )
    return await vault_svc.create_wallet(
        pool,
        owner,
        VaultWalletCreate(name=name, url="https://vault.corp", api_key_secret_id=key.id),
    )


async def test_create_local_secret_default_storage(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "st-local@example.com")
    s = await vault_svc.create_secret(
        db_pool, owner, VaultSecretCreate(label="L", slug="l", value="v"), enc_key=_ENC
    )
    assert s.storage_type == "local"
    assert s.vault_identifier is None and s.vault_path is None
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_create_vault_secret(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "st-vault@example.com")
    await _endpoint(db_pool, owner, "corp-a")
    s = await vault_svc.create_secret(
        db_pool,
        owner,
        VaultSecretCreate(
            label="DB", slug="db", storage_type="vault",
            vault_identifier="corp-a", vault_path="/infra/db",
        ),
        enc_key=_ENC,
    )
    assert s.storage_type == "vault"
    assert s.vault_identifier == "corp-a"
    assert s.vault_path == "/infra/db"
    # value_enc NULL en base
    ve = await db_pool.fetchval("SELECT value_enc FROM user_secret WHERE id = $1", s.id)
    assert ve is None
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_create_vault_secret_unknown_endpoint_refused(db_pool: asyncpg.Pool) -> None:
    """Fail closed : endpoint inexistant → 422, jamais de repli en local."""
    owner = await _owner(db_pool, "st-noendpoint@example.com")
    with pytest.raises(HTTPException) as exc:
        await vault_svc.create_secret(
            db_pool, owner,
            VaultSecretCreate(
                label="X", slug="x", storage_type="vault",
                vault_identifier="nexistepas", vault_path="/p",
            ),
            enc_key=_ENC,
        )
    assert exc.value.status_code == 422
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_local_secret_rejects_vault_fields(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "st-mix@example.com")
    with pytest.raises(HTTPException) as exc:
        await vault_svc.create_secret(
            db_pool, owner,
            VaultSecretCreate(
                label="X", slug="x", value="v",
                storage_type="local", vault_identifier="corp-a",
            ),
            enc_key=_ENC,
        )
    assert exc.value.status_code == 422
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_vault_secret_requires_path(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "st-nopath@example.com")
    await _endpoint(db_pool, owner, "corp-b")
    with pytest.raises(HTTPException) as exc:
        await vault_svc.create_secret(
            db_pool, owner,
            VaultSecretCreate(label="X", slug="x", storage_type="vault", vault_identifier="corp-b"),
            enc_key=_ENC,
        )
    assert exc.value.status_code == 422
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_harpocrate_api_key_must_be_local(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "st-keyvault@example.com")
    await _endpoint(db_pool, owner, "corp-c")
    with pytest.raises(HTTPException) as exc:
        await vault_svc.create_secret(
            db_pool, owner,
            VaultSecretCreate(
                label="K", slug="k2", storage_type="vault",
                vault_identifier="corp-c", vault_path="/p", secret_type="HARPOCRATE_API_KEY",
            ),
            enc_key=_ENC,
        )
    assert exc.value.status_code == 422
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_resolve_vault_backed_secret(db_pool: asyncpg.Pool) -> None:
    """`${secret://uuid}` d'un secret vault → résolution via l'endpoint (SDK)."""
    owner = await _owner(db_pool, "st-resolve@example.com")
    await _endpoint(db_pool, owner, "corp-d")
    s = await vault_svc.create_secret(
        db_pool, owner,
        VaultSecretCreate(
            label="DB", slug="db2", storage_type="vault",
            vault_identifier="corp-d", vault_path="/infra/db",
        ),
        enc_key=_ENC,
    )
    mock_secrets = MagicMock()
    mock_secrets.get.return_value = "resolved_db_value"
    mock_client = MagicMock()
    mock_client.secrets = mock_secrets
    with patch("harpocrate.VaultClient", return_value=mock_client):
        value = await vault_svc.resolve_user_secret_value(
            db_pool, s.id, _ENC, harpocrate_url="https://global"
        )
    assert value == "resolved_db_value"
    mock_secrets.get.assert_called_once_with("/infra/db")
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


def test_create_backend_dispatch() -> None:
    pool = MagicMock()
    assert isinstance(create_backend("local", pool=pool, enc_key="k"), LocalBackend)
    assert isinstance(
        create_backend("vault", pool=pool, enc_key="k", harpocrate_url="u"), HarpocrateBackend
    )
    with pytest.raises(ValueError, match="storage_type"):
        create_backend("bogus", pool=pool, enc_key="k")


async def test_local_backend_decrypts(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "st-localbackend@example.com")
    s = await vault_svc.create_secret(
        db_pool, owner, VaultSecretCreate(label="L", slug="l", value="topsecret"), enc_key=_ENC
    )
    val = await vault_svc.resolve_user_secret_value(db_pool, s.id, _ENC)
    assert val == "topsecret"
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)

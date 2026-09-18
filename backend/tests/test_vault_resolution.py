"""T4 (E4) — Résolution robuste (STANDARD Harpocrate §6).

Cache des valeurs (pas de cache négatif), réutilisation du client, invalidation
401/403 + 1 retry, backoff réseau, messages nommant endpoint+chemin (jamais le
token). Validation de résolubilité à la configuration + intégrité de suppression.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
from fastapi import HTTPException
from harpocrate.exceptions import PermissionDenied, VaultHttpError

from docflow.schemas.vault import VaultSecretCreate, VaultWalletCreate
from docflow.secrets import vault_fetch
from docflow.vault import service as vault_svc

_ENC = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def _client(get_return: str | None = None, get_side_effect: list[object] | None = None):
    sec = MagicMock()
    if get_side_effect is not None:
        sec.get.side_effect = get_side_effect
    else:
        sec.get.return_value = get_return
    client = MagicMock()
    client.secrets = sec
    return client, sec


async def _fetch(**kw: object) -> str:
    defaults: dict[str, object] = dict(
        pool=MagicMock(), enc_key="k", identifier="corp", path="/p",
        harpocrate_url="https://h", backoff_base=0,
    )
    defaults.update(kw)
    return await vault_fetch.fetch_vault_secret(**defaults)  # type: ignore[arg-type]


# ── Cache + réutilisation du client ───────────────────────────────────────────


async def test_value_cached_and_client_reused() -> None:
    client, sec = _client(get_return="V")
    with patch("docflow.vault.service.get_api_key", new=AsyncMock(return_value=("tok", None))):
        with patch("harpocrate.VaultClient", return_value=client) as cls:
            assert await _fetch() == "V"
            assert await _fetch() == "V"
    assert sec.get.call_count == 1  # 2e appel servi par le cache
    assert cls.call_count == 1  # client réutilisé (pas reconstruit)


async def test_no_negative_cache() -> None:
    client, sec = _client(get_side_effect=[VaultHttpError(500, "boom"), "OK"])
    with patch("docflow.vault.service.get_api_key", new=AsyncMock(return_value=("tok", None))):
        with patch("harpocrate.VaultClient", return_value=client):
            with pytest.raises(ValueError):
                await _fetch()
            assert await _fetch() == "OK"  # pas de cache négatif → re-tenté
    assert sec.get.call_count == 2


# ── Invalidation 401/403 + une seule nouvelle tentative ───────────────────────


async def test_invalidate_on_401_retries_once() -> None:
    client, sec = _client(get_side_effect=[VaultHttpError(401, "stale"), "OK"])
    with patch("docflow.vault.service.get_api_key", new=AsyncMock(return_value=("tok", None))):
        with patch("harpocrate.VaultClient", return_value=client):
            assert await _fetch() == "OK"
    assert sec.get.call_count == 2


async def test_401_twice_raises_naming_endpoint_not_token() -> None:
    client, sec = _client(get_side_effect=[VaultHttpError(401), VaultHttpError(401)])
    with patch(
        "docflow.vault.service.get_api_key",
        new=AsyncMock(return_value=("supersecrettoken", None)),
    ):
        with patch("harpocrate.VaultClient", return_value=client):
            with pytest.raises(ValueError) as exc:
                await _fetch(identifier="corp", path="/db")
    msg = str(exc.value)
    assert "corp" in msg and "/db" in msg
    assert "supersecrettoken" not in msg
    assert sec.get.call_count == 2


async def test_permission_denied_retries_then_raises() -> None:
    client, sec = _client(get_side_effect=[PermissionDenied("no"), PermissionDenied("no")])
    with patch("docflow.vault.service.get_api_key", new=AsyncMock(return_value=("tok", None))):
        with patch("harpocrate.VaultClient", return_value=client):
            with pytest.raises(ValueError, match="corp"):
                await _fetch()
    assert sec.get.call_count == 2


# ── Backoff réseau ────────────────────────────────────────────────────────────


async def test_network_error_backoff_retry() -> None:
    client, sec = _client(get_side_effect=[VaultHttpError(0, "conn failed"), "OK"])
    with patch("docflow.vault.service.get_api_key", new=AsyncMock(return_value=("tok", None))):
        with patch("harpocrate.VaultClient", return_value=client):
            assert await _fetch(backoff_base=0) == "OK"
    assert sec.get.call_count == 2


async def test_unknown_endpoint_raises_naming_it() -> None:
    with patch("docflow.vault.service.get_api_key", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="corp"):
            await _fetch(identifier="corp")


# ── Validation de résolubilité à la configuration + intégrité ─────────────────


async def _owner(pool: asyncpg.Pool, email: str) -> asyncpg.Record:
    return await pool.fetchval(
        "INSERT INTO app_user (email, label, source, validated, is_admin) "
        "VALUES ($1, 'T', 'local', true, true) RETURNING id",
        email,
    )


async def _endpoint(pool: asyncpg.Pool, owner: asyncpg.Record, name: str):
    key = await vault_svc.create_secret(
        pool, owner,
        VaultSecretCreate(
            label="K", slug=f"k-{name}", value="hrpv_1_tok", secret_type="HARPOCRATE_API_KEY"
        ),
        enc_key=_ENC,
    )
    return await vault_svc.create_wallet(
        pool, owner,
        VaultWalletCreate(name=name, url="https://vault.corp", api_key_secret_id=key.id),
    )


async def test_assert_refs_resolvable_unknown_vault(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await vault_svc.assert_refs_resolvable(db_pool, ["${vault://nope:/p}"])
    assert exc.value.status_code == 422


async def test_assert_refs_resolvable_ok(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "res-ok@example.com")
    await _endpoint(db_pool, owner, "corpx")
    await vault_svc.assert_refs_resolvable(db_pool, ["${vault://corpx:/p}"])  # ne lève pas
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_delete_endpoint_refused_when_vault_secret_references_it(
    db_pool: asyncpg.Pool,
) -> None:
    owner = await _owner(db_pool, "res-del@example.com")
    ep = await _endpoint(db_pool, owner, "corpy")
    await vault_svc.create_secret(
        db_pool, owner,
        VaultSecretCreate(
            label="DB", slug="db", storage_type="vault",
            vault_identifier="corpy", vault_path="/p",
        ),
        enc_key=_ENC,
    )
    with pytest.raises(HTTPException) as exc:
        await vault_svc.delete_wallet(db_pool, owner, ep.id)
    assert exc.value.status_code == 409
    assert "db" in exc.value.detail.get("secrets", [])
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)

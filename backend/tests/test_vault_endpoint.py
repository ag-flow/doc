"""T2 (E3) — Endpoint vault propre.

L'endpoint ne contient plus le token : il porte un propriétaire, une URL, une
description, et RÉFÉRENCE un secret local typé HARPOCRATE_API_KEY. L'alias `name`
reste global (résolution sans session). Gestion scoped-owner + suppression
protégée croisée (secret clé refusé tant qu'un endpoint le référence).
"""

from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.schemas.vault import VaultSecretCreate, VaultWalletCreate
from docflow.vault import service as vault_svc

_ENC = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


async def _owner(pool: asyncpg.Pool, email: str) -> asyncpg.Record:
    return await pool.fetchval(
        "INSERT INTO app_user (email, label, source, validated, is_admin) "
        "VALUES ($1, 'T', 'local', true, true) RETURNING id",
        email,
    )


async def _api_key_secret(pool: asyncpg.Pool, owner: asyncpg.Record, slug: str = "cle-coffre"):
    return await vault_svc.create_secret(
        pool,
        owner,
        VaultSecretCreate(
            label="Clé", slug=slug, value="hrpv_1_realtoken", secret_type="HARPOCRATE_API_KEY"
        ),
        enc_key=_ENC,
    )


async def test_create_endpoint_references_local_key(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "ep-create@example.com")
    key = await _api_key_secret(db_pool, owner)
    ep = await vault_svc.create_wallet(
        db_pool,
        owner,
        VaultWalletCreate(
            name="corp", url="https://vault.example.com",
            description="Coffre corp", api_key_secret_id=key.id,
        ),
    )
    assert ep.name == "corp"
    assert ep.url == "https://vault.example.com"
    assert ep.description == "Coffre corp"
    assert ep.api_key_secret_id == key.id
    assert ep.api_key_secret_label == "Clé"
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_create_endpoint_rejects_non_harpocrate_secret(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "ep-badtype@example.com")
    generic = await vault_svc.create_secret(
        db_pool, owner, VaultSecretCreate(label="G", slug="g", value="x"), enc_key=_ENC
    )
    with pytest.raises(HTTPException) as exc:
        await vault_svc.create_wallet(
            db_pool, owner,
            VaultWalletCreate(name="corp2", url="https://v", api_key_secret_id=generic.id),
        )
    assert exc.value.status_code == 422
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_create_endpoint_rejects_foreign_secret(db_pool: asyncpg.Pool) -> None:
    a = await _owner(db_pool, "ep-a@example.com")
    b = await _owner(db_pool, "ep-b@example.com")
    key_a = await _api_key_secret(db_pool, a)
    with pytest.raises(HTTPException) as exc:
        await vault_svc.create_wallet(
            db_pool, b,
            VaultWalletCreate(name="corp3", url="https://v", api_key_secret_id=key_a.id),
        )
    assert exc.value.status_code in (403, 422)
    await db_pool.execute("DELETE FROM app_user WHERE id = ANY($1::uuid[])", [a, b])


async def test_get_api_key_resolves_via_reference(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "ep-resolve@example.com")
    key = await _api_key_secret(db_pool, owner)
    await vault_svc.create_wallet(
        db_pool, owner,
        VaultWalletCreate(name="corp4", url="https://vault.corp", api_key_secret_id=key.id),
    )
    resolved = await vault_svc.get_api_key(db_pool, "corp4", _ENC)
    assert resolved is not None
    api_key, url = resolved
    assert api_key == "hrpv_1_realtoken"
    assert url == "https://vault.corp"
    assert await vault_svc.get_api_key(db_pool, "inconnu", _ENC) is None
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_delete_api_key_secret_refused_when_referenced(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "ep-guard@example.com")
    key = await _api_key_secret(db_pool, owner)
    await vault_svc.create_wallet(
        db_pool, owner,
        VaultWalletCreate(name="corp5", url="https://v", api_key_secret_id=key.id),
    )
    with pytest.raises(HTTPException) as exc:
        await vault_svc.delete_secret(db_pool, owner, key.id, _ENC)
    assert exc.value.status_code == 409
    assert isinstance(exc.value.detail, dict)
    assert "corp5" in exc.value.detail.get("endpoints", [])
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_endpoints_scoped_to_owner(db_pool: asyncpg.Pool) -> None:
    a = await _owner(db_pool, "ep-scope-a@example.com")
    b = await _owner(db_pool, "ep-scope-b@example.com")
    ka = await _api_key_secret(db_pool, a)
    await vault_svc.create_wallet(
        db_pool, a,
        VaultWalletCreate(name="corp6", url="https://v", api_key_secret_id=ka.id),
    )
    assert [w.name for w in await vault_svc.list_wallets(db_pool, a)] == ["corp6"]
    assert await vault_svc.list_wallets(db_pool, b) == []
    await db_pool.execute("DELETE FROM app_user WHERE id = ANY($1::uuid[])", [a, b])

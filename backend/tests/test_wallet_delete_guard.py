"""STANDARD Harpocrate §4 — un endpoint référencé ne se supprime pas (409 + liste)."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.automations import service as auto_svc
from docflow.schemas.automations import AutomationCreate, AutomationHeaderIn
from docflow.schemas.vault import VaultSecretCreate, VaultWalletCreate
from docflow.vault import service as vault_svc

_UPDATED = "docflow.document.updated.v1"
_ENC = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


async def _ws(pool: asyncpg.Pool) -> str:
    slug = f"wg-{uuid.uuid4().hex[:8]}"
    await pool.execute("INSERT INTO workspace (slug, label) VALUES ($1, $2)", slug, "WG")
    return slug


async def _owner(pool: asyncpg.Pool) -> asyncpg.Record:
    return await pool.fetchval(
        "INSERT INTO app_user (email, label, source, validated, is_admin) "
        "VALUES ($1, 'T', 'local', true, true) RETURNING id",
        f"wg-{uuid.uuid4().hex[:8]}@example.com",
    )


async def _endpoint(pool: asyncpg.Pool, owner: asyncpg.Record, name: str):
    key = await vault_svc.create_secret(
        pool,
        owner,
        VaultSecretCreate(
            label=f"K {name}", slug=f"k-{name}", value="hrpv_1_x",
            secret_type="HARPOCRATE_API_KEY",
        ),
        enc_key=_ENC,
    )
    return await vault_svc.create_wallet(
        pool, owner, VaultWalletCreate(name=name, url="https://v", api_key_secret_id=key.id)
    )


async def test_delete_wallet_refused_while_referenced(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool)
    name = f"cofre{uuid.uuid4().hex[:6]}"
    wallet = await _endpoint(db_pool, owner, name)

    ws = await _ws(db_pool)
    await auto_svc.create_automation(
        db_pool,
        ws,
        AutomationCreate(
            label="Rag",
            event_codes=[_UPDATED],
            url="https://rag.example/api",
            http_method="POST",
            headers=[AutomationHeaderIn(name="Authorization", secret_ref=f"${{vault://{name}:/p}}")],
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await vault_svc.delete_wallet(db_pool, owner, wallet.id)
    assert exc.value.status_code == 409
    assert "automate" in exc.value.detail["message"]
    assert await db_pool.fetchval("SELECT 1 FROM vault_wallet WHERE id = $1", wallet.id)
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_delete_unused_wallet_succeeds(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool)
    wallet = await _endpoint(db_pool, owner, f"libre{uuid.uuid4().hex[:6]}")
    await vault_svc.delete_wallet(db_pool, owner, wallet.id)
    assert not await db_pool.fetchval("SELECT 1 FROM vault_wallet WHERE id = $1", wallet.id)
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_delete_wallet_name_prefix_not_confused(db_pool: asyncpg.Pool) -> None:
    """Deux endpoints dont l'un est préfixe de l'autre : supprimer le court ne doit
    pas être bloqué par une réf du long (match de préfixe EXACT, `:` inclus)."""
    owner = await _owner(db_pool)
    short = await _endpoint(db_pool, owner, "cofrex")
    await _endpoint(db_pool, owner, "cofrexlong")
    ws = await _ws(db_pool)
    await auto_svc.create_automation(
        db_pool,
        ws,
        AutomationCreate(
            label="L",
            event_codes=[_UPDATED],
            url="https://x/api",
            http_method="POST",
            headers=[AutomationHeaderIn(name="A", secret_ref="${vault://cofrexlong:/p}")],
        ),
    )
    await vault_svc.delete_wallet(db_pool, owner, short.id)
    assert not await db_pool.fetchval("SELECT 1 FROM vault_wallet WHERE id = $1", short.id)
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)

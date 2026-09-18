"""STANDARD Harpocrate §4 — un coffre référencé ne se supprime pas (409 + liste)."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from docflow.automations import service as auto_svc
from docflow.schemas.automations import AutomationCreate, AutomationHeaderIn
from docflow.schemas.vault import VaultWalletCreate
from docflow.vault import service as vault_svc

_UPDATED = "docflow.document.updated.v1"


async def _ws(pool: asyncpg.Pool) -> str:
    slug = f"wg-{uuid.uuid4().hex[:8]}"
    await pool.execute("INSERT INTO workspace (slug, label) VALUES ($1, $2)", slug, "WG")
    return slug


async def test_delete_wallet_refused_while_referenced(db_pool: asyncpg.Pool) -> None:
    key = Fernet.generate_key().decode()
    name = f"cofre{uuid.uuid4().hex[:6]}"
    wallet = await vault_svc.create_wallet(db_pool, VaultWalletCreate(name=name, api_key="k"), key)

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
        await vault_svc.delete_wallet(db_pool, wallet.id)
    assert exc.value.status_code == 409
    assert "automate" in exc.value.detail["message"]
    # Le coffre est toujours là (suppression bloquée).
    assert await db_pool.fetchval("SELECT 1 FROM vault_wallet WHERE id = $1", wallet.id)


async def test_delete_unused_wallet_succeeds(db_pool: asyncpg.Pool) -> None:
    key = Fernet.generate_key().decode()
    wallet = await vault_svc.create_wallet(
        db_pool, VaultWalletCreate(name=f"libre{uuid.uuid4().hex[:6]}", api_key="k"), key
    )
    await vault_svc.delete_wallet(db_pool, wallet.id)
    assert not await db_pool.fetchval("SELECT 1 FROM vault_wallet WHERE id = $1", wallet.id)


async def test_delete_wallet_name_prefix_not_confused(db_pool: asyncpg.Pool) -> None:
    """Deux coffres dont l'un est préfixe de l'autre : supprimer le court ne doit
    pas être bloqué par une réf du long (match de préfixe EXACT, `:` inclus)."""
    key = Fernet.generate_key().decode()
    short = await vault_svc.create_wallet(
        db_pool, VaultWalletCreate(name="cofrex", api_key="k"), key
    )
    await vault_svc.create_wallet(db_pool, VaultWalletCreate(name="cofrexlong", api_key="k"), key)
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
    # « cofrex » n'est pas utilisé (seul « cofrexlong » l'est) → suppression OK.
    await vault_svc.delete_wallet(db_pool, short.id)
    assert not await db_pool.fetchval("SELECT 1 FROM vault_wallet WHERE id = $1", short.id)

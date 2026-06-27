from __future__ import annotations

import re
import uuid

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.crypto import decrypt_str, encrypt_str
from docflow.schemas.vault import VaultWalletCreate, VaultWalletOut

log = structlog.get_logger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


async def list_wallets(pool: asyncpg.Pool) -> list[VaultWalletOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, created_at, updated_at FROM vault_wallet ORDER BY name"
        )
    return [VaultWalletOut(**dict(row)) for row in rows]


async def create_wallet(
    pool: asyncpg.Pool, body: VaultWalletCreate, enc_key: str
) -> VaultWalletOut:
    if not _NAME_RE.match(body.name):
        raise HTTPException(422, "Nom invalide : minuscules, chiffres, tirets, underscores.")
    api_key_enc = encrypt_str(enc_key, body.api_key)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO vault_wallet (name, api_key_enc)
                VALUES ($1, $2)
                RETURNING id, name, created_at, updated_at
                """,
                body.name,
                api_key_enc,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(409, f"Un wallet nommé « {body.name} » existe déjà.") from exc
    assert row is not None
    return VaultWalletOut(**dict(row))


async def delete_wallet(pool: asyncpg.Pool, wallet_id: uuid.UUID) -> None:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM vault_wallet WHERE id = $1", wallet_id
        )
    if result == "DELETE 0":
        raise HTTPException(404, "Wallet introuvable.")


async def get_api_key(pool: asyncpg.Pool, name: str, enc_key: str) -> str | None:
    """Retourne la clé API déchiffrée pour un wallet, ou None si inconnu."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT api_key_enc FROM vault_wallet WHERE name = $1", name
        )
    if row is None:
        return None
    return decrypt_str(enc_key, row["api_key_enc"])

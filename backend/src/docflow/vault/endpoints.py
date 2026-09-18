"""Endpoints vault (coffres) : CRUD scoped-owner + résolution de la clé d'API.

L'endpoint référence un secret local `HARPOCRATE_API_KEY` (jamais le token inline).
Alias `name` GLOBAL (stabilité des références `${vault://alias:/path}`).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import asyncpg
from fastapi import HTTPException

from docflow.crypto import decrypt_str
from docflow.schemas.vault import VaultWalletCreate, VaultWalletOut, WalletCheckOut


async def _count_vault_consumers(conn: asyncpg.Connection, name: str) -> int:
    """Compte les consommateurs référençant `${vault://<name>:…}` (automates +
    producteur d'events). Préfixe EXACT (pas de LIKE : `_`/`-` seraient des jokers)."""
    prefix = f"${{vault://{name}:"
    autos = await conn.fetchval(
        "SELECT count(DISTINCT automation_ref) FROM automation_header "
        "WHERE left(secret_ref, char_length($1)) = $1",
        prefix,
    )
    prod = await conn.fetchval(
        "SELECT count(*) FROM events_producer_config WHERE left(secret_ref, char_length($1)) = $1",
        prefix,
    )
    return int(autos or 0) + int(prod or 0)


async def list_wallets(pool: asyncpg.Pool, owner_id: uuid.UUID) -> list[VaultWalletOut]:
    """Endpoints vault du propriétaire (gestion scoped-owner)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT w.id, w.name, w.url, w.description,
                   w.api_key_secret_ref AS api_key_secret_id,
                   s.label AS api_key_secret_label,
                   w.created_at, w.updated_at
            FROM vault_wallet w
            JOIN user_secret s ON s.id = w.api_key_secret_ref
            WHERE w.owner_ref = $1
            ORDER BY w.name
            """,
            owner_id,
        )
        out = [VaultWalletOut(**dict(row)) for row in rows]
        for ep in out:
            ep.used_by = await _count_vault_consumers(conn, ep.name)
    return out


async def create_wallet(
    pool: asyncpg.Pool, owner_id: uuid.UUID, body: VaultWalletCreate
) -> VaultWalletOut:
    """Crée un endpoint vault référençant un secret local `HARPOCRATE_API_KEY` du
    propriétaire. Le token n'est jamais saisi ici : seule sa référence l'est."""
    async with pool.acquire() as conn:
        sec = await conn.fetchrow(
            "SELECT label, secret_type FROM user_secret WHERE id = $1 AND owner_ref = $2",
            body.api_key_secret_id,
            owner_id,
        )
        if sec is None:
            raise HTTPException(
                422, "Clé d'API introuvable ou appartenant à un autre propriétaire."
            )
        if sec["secret_type"] != "HARPOCRATE_API_KEY":
            raise HTTPException(
                422, "La clé d'API référencée doit être un secret de type HARPOCRATE_API_KEY."
            )
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO vault_wallet (name, owner_ref, url, description, api_key_secret_ref)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, name, url, description,
                          api_key_secret_ref AS api_key_secret_id, created_at, updated_at
                """,
                body.name,
                owner_id,
                body.url,
                body.description,
                body.api_key_secret_id,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(409, f"Un endpoint nommé « {body.name} » existe déjà.") from exc
    assert row is not None
    return VaultWalletOut(**dict(row), api_key_secret_label=sec["label"])


async def delete_wallet(pool: asyncpg.Pool, owner_id: uuid.UUID, wallet_id: uuid.UUID) -> None:
    """Supprime un endpoint du propriétaire. Refusé (409) tant qu'un consommateur
    référence encore `${vault://<nom>:…}` (automate ou producteur d'events) — sinon
    la résolution échouerait silencieusement à l'exécution (STANDARD Harpocrate §4)."""
    async with pool.acquire() as conn:
        name = await conn.fetchval(
            "SELECT name FROM vault_wallet WHERE id = $1 AND owner_ref = $2", wallet_id, owner_id
        )
        if name is None:
            raise HTTPException(404, "Endpoint introuvable.")
        prefix = f"${{vault://{name}:"
        autos = await conn.fetch(
            "SELECT DISTINCT a.label FROM automation_header h "
            "JOIN automation a ON a.id = h.automation_ref "
            "WHERE left(h.secret_ref, char_length($1)) = $1 ORDER BY a.label",
            prefix,
        )
        producer = await conn.fetchval(
            "SELECT 1 FROM events_producer_config WHERE left(secret_ref, char_length($1)) = $1",
            prefix,
        )
        # Secrets vault-backed pointant cet endpoint (intégrité de résolubilité).
        vault_secrets = [
            r["slug"]
            for r in await conn.fetch(
                "SELECT slug FROM user_secret WHERE vault_identifier = $1 ORDER BY slug", name
            )
        ]
        if autos or producer or vault_secrets:
            labels = [r["label"] for r in autos]
            parts = []
            if labels:
                parts.append(f"{len(labels)} automate(s)")
            if producer:
                parts.append("le producteur d'events")
            if vault_secrets:
                parts.append(f"{len(vault_secrets)} secret(s)")
            raise HTTPException(
                409,
                {
                    "message": "endpoint utilisé par " + " et ".join(parts),
                    "automations": labels,
                    "producer": bool(producer),
                    "secrets": vault_secrets,
                },
            )
        await conn.execute(
            "DELETE FROM vault_wallet WHERE id = $1 AND owner_ref = $2", wallet_id, owner_id
        )


async def get_api_key(pool: asyncpg.Pool, name: str, enc_key: str) -> tuple[str, str | None] | None:
    """Résout (token, url) d'un endpoint par son alias global, sans session.

    Chaîne : endpoint → secret clé d'API local → valeur déchiffrée. `url` peut être
    None pour un endpoint migré (repli sur l'URL globale côté appelant)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT s.value_enc, w.url FROM vault_wallet w "
            "JOIN user_secret s ON s.id = w.api_key_secret_ref WHERE w.name = $1",
            name,
        )
    if row is None:
        return None
    return decrypt_str(enc_key, row["value_enc"]), row["url"]


async def check_wallet(
    pool: asyncpg.Pool,
    owner_id: uuid.UUID,
    wallet_id: uuid.UUID,
    enc_key: str,
    harpocrate_url: str | None,
) -> WalletCheckOut:
    """Teste la clé d'un endpoint du propriétaire auprès de Harpocrate.

    Résout le token via le secret référencé ; utilise l'URL de l'endpoint (repli
    sur l'URL globale). N'expose jamais la clé — seulement l'état et l'échéance.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT w.url, s.value_enc FROM vault_wallet w "
            "JOIN user_secret s ON s.id = w.api_key_secret_ref "
            "WHERE w.id = $1 AND w.owner_ref = $2",
            wallet_id,
            owner_id,
        )
    if row is None:
        raise HTTPException(404, "Endpoint introuvable.")
    url = row["url"] or harpocrate_url
    if not url:
        return WalletCheckOut(ok=False, error="URL du coffre non configurée.")

    api_key = decrypt_str(enc_key, row["value_enc"])

    def _probe() -> WalletCheckOut:
        from harpocrate import VaultClient

        client = VaultClient(token=api_key, base_url=url)
        info = client.whoami()
        expires = getattr(info, "expires_at", None)
        return WalletCheckOut(
            ok=True,
            expires_at=(
                datetime.fromtimestamp(expires, tz=UTC)
                if isinstance(expires, (int, float))
                else expires
            ),
        )

    try:
        return await asyncio.to_thread(_probe)
    except Exception as exc:
        return WalletCheckOut(ok=False, error=str(exc))

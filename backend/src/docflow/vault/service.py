from __future__ import annotations

import re
import secrets as _secrets
import uuid

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.crypto import decrypt_str, encrypt_str
from docflow.schemas.vault import (
    HmacSecretCreate,
    HmacSecretCreated,
    HmacSecretOut,
    VaultSecretCreate,
    VaultSecretOut,
    VaultWalletCreate,
    VaultWalletOut,
)

# Longueur (octets) d'un secret HMAC généré → token_urlsafe.
_HMAC_SECRET_BYTES = 32

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
        result = await conn.execute("DELETE FROM vault_wallet WHERE id = $1", wallet_id)
    if result == "DELETE 0":
        raise HTTPException(404, "Wallet introuvable.")


async def get_api_key(pool: asyncpg.Pool, name: str, enc_key: str) -> str | None:
    """Retourne la clé API déchiffrée pour un wallet, ou None si inconnu."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT api_key_enc FROM vault_wallet WHERE name = $1", name)
    if row is None:
        return None
    return decrypt_str(enc_key, row["api_key_enc"])


# ── Secrets utilisateur ───────────────────────────────────────────────────────


async def list_secrets(pool: asyncpg.Pool, user_id: uuid.UUID) -> list[VaultSecretOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.slug, s.label, s.created_at, s.updated_at,
                   (SELECT count(*) FROM automation_header h
                     WHERE h.secret_ref = '${secret://' || s.id || '}') AS used_by_automations
            FROM user_secret s
            WHERE s.owner_ref = $1 AND s.kind = 'generic'
            ORDER BY s.label
            """,
            user_id,
        )
    return [VaultSecretOut(**dict(row)) for row in rows]


async def create_secret(
    pool: asyncpg.Pool,
    user_id: uuid.UUID,
    body: VaultSecretCreate,
    enc_key: str,
) -> VaultSecretOut:
    value_enc = encrypt_str(enc_key, body.value)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO user_secret (owner_ref, slug, label, value_enc)
                VALUES ($1, $2, $3, $4)
                RETURNING id, slug, label, created_at, updated_at
                """,
                user_id,
                body.slug,
                body.label,
                value_enc,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(409, f"Un secret nommé « {body.slug} » existe déjà.") from exc
    assert row is not None
    return VaultSecretOut(**dict(row))


async def delete_secret(
    pool: asyncpg.Pool,
    user_id: uuid.UUID,
    secret_id: uuid.UUID,
) -> None:
    async with pool.acquire() as conn:
        # Refus motivé : un secret référencé par des automates ne se supprime
        # pas — l'appel échouerait à la résolution. La liste est retournée.
        rows = await conn.fetch(
            "SELECT DISTINCT a.label FROM automation_header h "
            "JOIN automation a ON a.id = h.automation_ref "
            "WHERE h.secret_ref = '${secret://' || $1::uuid || '}' ORDER BY a.label",
            secret_id,
        )
        if rows:
            labels = [r["label"] for r in rows]
            raise HTTPException(
                409,
                {
                    "message": f"secret utilisé par {len(labels)} automate(s)",
                    "automations": labels,
                },
            )
        result = await conn.execute(
            "DELETE FROM user_secret WHERE id = $1 AND owner_ref = $2",
            secret_id,
            user_id,
        )
    if result == "DELETE 0":
        raise HTTPException(404, "Secret introuvable.")


# ── Secrets HMAC (partagés, copiables par leur propriétaire) ──────────────────


async def list_hmac_secrets(pool: asyncpg.Pool, user_id: uuid.UUID) -> list[HmacSecretOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, slug, label, created_at, updated_at
            FROM user_secret
            WHERE owner_ref = $1 AND kind = 'hmac'
            ORDER BY label
            """,
            user_id,
        )
    return [HmacSecretOut(**dict(row)) for row in rows]


async def create_hmac_secret(
    pool: asyncpg.Pool,
    user_id: uuid.UUID,
    body: HmacSecretCreate,
    enc_key: str,
) -> HmacSecretCreated:
    """Crée un secret HMAC. Valeur fournie, ou générée aléatoirement si absente.

    La valeur effective est renvoyée UNE fois (copie immédiate côté client).
    """
    value = body.value if body.value else _secrets.token_urlsafe(_HMAC_SECRET_BYTES)
    value_enc = encrypt_str(enc_key, value)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO user_secret (owner_ref, slug, label, value_enc, kind)
                VALUES ($1, $2, $3, $4, 'hmac')
                RETURNING id, slug, label, created_at, updated_at
                """,
                user_id,
                body.slug,
                body.label,
                value_enc,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(409, f"Un secret nommé « {body.slug} » existe déjà.") from exc
    assert row is not None
    return HmacSecretCreated(**dict(row), value=value)


async def reveal_hmac_secret(
    pool: asyncpg.Pool,
    user_id: uuid.UUID,
    secret_id: uuid.UUID,
    enc_key: str,
) -> str:
    """Déchiffre et retourne la valeur d'un secret HMAC du propriétaire.

    Exception ASSUMÉE à l'invariant « valeur jamais révélée » : le secret HMAC
    est symétrique et partagé, il doit être copiable pour être renseigné côté
    pair. Réservé à kind = 'hmac' et au propriétaire.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value_enc FROM user_secret "
            "WHERE id = $1 AND owner_ref = $2 AND kind = 'hmac'",
            secret_id,
            user_id,
        )
    if row is None:
        raise HTTPException(404, "Secret HMAC introuvable.")
    return decrypt_str(enc_key, row["value_enc"])


async def resolve_user_secret_value(
    pool: asyncpg.Pool, secret_id: uuid.UUID, enc_key: str
) -> str | None:
    """Résout la valeur d'un secret utilisateur par son id (tous kinds).

    Utilisé par le résolveur `${secret://<uuid>}` (worker d'automate) pour
    injecter une valeur secrète (ex. clé API externe) dans un header. Résolution
    par id global, côté serveur — la valeur n'est jamais renvoyée à l'API.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value_enc FROM user_secret WHERE id = $1", secret_id
        )
    if row is None:
        return None
    return decrypt_str(enc_key, row["value_enc"])


async def resolve_hmac_value(
    pool: asyncpg.Pool, secret_id: uuid.UUID, enc_key: str
) -> str | None:
    """Résout la valeur d'un secret HMAC par son id (sans contexte utilisateur).

    Utilisé par le résolveur `${hmac://<uuid>}` (worker d'émission) : la
    référence porte l'id global (PK), non ambigu même si le store est par-user.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value_enc FROM user_secret WHERE id = $1 AND kind = 'hmac'",
            secret_id,
        )
    if row is None:
        return None
    return decrypt_str(enc_key, row["value_enc"])

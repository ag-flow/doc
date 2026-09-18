"""Secrets HMAC : symétriques et partagés avec le pair (workflow).

Exception ASSUMÉE à l'invariant « valeur jamais révélée » : un secret HMAC doit
rester copiable par son propriétaire pour être renseigné côté pair (kind='hmac').
"""

from __future__ import annotations

import secrets as _secrets
import uuid

import asyncpg
from fastapi import HTTPException

from docflow.crypto import decrypt_str, encrypt_str
from docflow.schemas.vault import HmacSecretCreate, HmacSecretCreated, HmacSecretOut

# Longueur (octets) d'un secret HMAC généré → token_urlsafe.
_HMAC_SECRET_BYTES = 32


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

    Réservé à kind = 'hmac' et au propriétaire.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value_enc FROM user_secret WHERE id = $1 AND owner_ref = $2 AND kind = 'hmac'",
            secret_id,
            user_id,
        )
    if row is None:
        raise HTTPException(404, "Secret HMAC introuvable.")
    return decrypt_str(enc_key, row["value_enc"])


async def resolve_hmac_value(pool: asyncpg.Pool, secret_id: uuid.UUID, enc_key: str) -> str | None:
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

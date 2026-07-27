from __future__ import annotations

import asyncio
import re
import secrets as _secrets
import uuid
from datetime import UTC, datetime

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
    WalletCheckOut,
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


async def list_secrets(
    pool: asyncpg.Pool, user_id: uuid.UUID, enc_key: str | None = None
) -> list[VaultSecretOut]:
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
    out = [VaultSecretOut(**dict(row)) for row in rows]
    # Usage côté webhooks : headers chiffrés, scannés côté serveur.
    for secret in out:
        secret.used_by_webhooks = len(
            await _webhooks_referencing_secret(pool, secret.id, enc_key)
        )
    return out


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


async def _webhooks_referencing_secret(
    pool: asyncpg.Pool, secret_id: uuid.UUID, enc_key: str | None
) -> list[str]:
    """Webhooks (tous workspaces) dont un header référence ${secret://<id>}.

    Les headers sont chiffrés : on les déchiffre côté serveur pour le comptage.
    Sans clé de chiffrement, aucun comptage possible → liste vide (les refs ne
    seraient de toute façon pas résolues à l'envoi non plus).
    """
    if not enc_key:
        return []
    from docflow.crypto import decrypt_headers

    needle = f"${{secret://{secret_id}}}"
    rows = await pool.fetch(
        "SELECT w.label, w.headers_encrypted, ws.slug AS ws_slug "
        "FROM webhook_subscription w "
        "JOIN workspace ws ON ws.workspace_technical_key = w.workspace_technical_key "
        "WHERE w.headers_encrypted IS NOT NULL ORDER BY ws.slug, w.label"
    )
    hits: list[str] = []
    for r in rows:
        try:
            headers = decrypt_headers(enc_key, r["headers_encrypted"])
        except Exception:
            continue
        if any(v == needle for v in headers.values()):
            hits.append(f"{r['ws_slug']} / {r['label']}")
    return hits


async def delete_secret(
    pool: asyncpg.Pool,
    user_id: uuid.UUID,
    secret_id: uuid.UUID,
    enc_key: str | None = None,
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
        webhooks = await _webhooks_referencing_secret(pool, secret_id, enc_key)
        if rows or webhooks:
            labels = [r["label"] for r in rows]
            parts = []
            if labels:
                parts.append(f"{len(labels)} automate(s)")
            if webhooks:
                parts.append(f"{len(webhooks)} webhook(s)")
            raise HTTPException(
                409,
                {
                    "message": "secret utilisé par " + " et ".join(parts),
                    "automations": labels,
                    "webhooks": webhooks,
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


async def check_wallet(
    pool: asyncpg.Pool,
    wallet_id: uuid.UUID,
    enc_key: str,
    harpocrate_url: str | None,
) -> WalletCheckOut:
    """Teste la clé du wallet auprès de Harpocrate : jeton valide, expiration.

    N'expose jamais la clé — seulement l'état et l'échéance du jeton.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name, api_key_enc FROM vault_wallet WHERE id = $1", wallet_id
        )
    if row is None:
        raise HTTPException(404, "Wallet introuvable.")
    if not harpocrate_url:
        return WalletCheckOut(ok=False, error="HARPOCRATE_URL non configurée sur l'instance.")

    api_key = decrypt_str(enc_key, row["api_key_enc"])

    def _probe() -> WalletCheckOut:
        from harpocrate import VaultClient

        client = VaultClient(token=api_key, base_url=harpocrate_url)
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

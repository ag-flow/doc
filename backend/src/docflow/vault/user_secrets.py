"""Secrets utilisateur : génériques (`${secret://}`), HMAC (`${hmac://}`), et
résolution serveur (local Fernet ou vault via la fabrique de backends).
"""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.crypto import encrypt_str
from docflow.schemas.vault import VaultSecretCreate, VaultSecretOut


async def list_secrets(
    pool: asyncpg.Pool,
    user_id: uuid.UUID,
    enc_key: str | None = None,
    secret_type: str | None = None,
) -> list[VaultSecretOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.slug, s.label, s.secret_type,
                   s.storage_type, s.vault_identifier, s.vault_path,
                   s.created_at, s.updated_at,
                   (SELECT count(*) FROM automation_header h
                     WHERE h.secret_ref = '${secret://' || s.id || '}') AS used_by_automations
            FROM user_secret s
            WHERE s.owner_ref = $1 AND s.kind = 'generic'
              AND ($2::text IS NULL OR s.secret_type = $2)
            ORDER BY s.label
            """,
            user_id,
            secret_type,
        )
    out = [VaultSecretOut(**dict(row)) for row in rows]
    # Usage côté webhooks : headers chiffrés, scannés côté serveur.
    for secret in out:
        secret.used_by_webhooks = len(await _webhooks_referencing_secret(pool, secret.id, enc_key))
    return out


async def create_secret(
    pool: asyncpg.Pool,
    user_id: uuid.UUID,
    body: VaultSecretCreate,
    enc_key: str,
) -> VaultSecretOut:
    if body.secret_type == "HARPOCRATE_API_KEY" and body.storage_type != "local":
        raise HTTPException(422, "Un secret HARPOCRATE_API_KEY doit être stocké en local.")
    async with pool.acquire() as conn:
        if body.storage_type == "local":
            if not body.value:
                raise HTTPException(422, "Valeur requise pour un secret local.")
            if body.vault_identifier or body.vault_path:
                raise HTTPException(422, "Champs vault interdits pour un stockage local.")
            value_enc: str | None = encrypt_str(enc_key, body.value)
            vault_identifier: str | None = None
            vault_path: str | None = None
        else:  # vault — aucun repli automatique (fail closed)
            if body.value:
                raise HTTPException(
                    422, "Valeur interdite : le coffre détient la valeur d'un secret vault."
                )
            if not body.vault_identifier or not body.vault_path:
                raise HTTPException(422, "Endpoint et chemin requis pour un stockage vault.")
            exists = await conn.fetchval(
                "SELECT 1 FROM vault_wallet WHERE name = $1 AND owner_ref = $2",
                body.vault_identifier,
                user_id,
            )
            if not exists:
                raise HTTPException(
                    422, f"Endpoint vault « {body.vault_identifier} » inexistant : aucun repli."
                )
            value_enc = None
            vault_identifier = body.vault_identifier
            vault_path = body.vault_path
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO user_secret
                    (owner_ref, slug, label, value_enc, secret_type,
                     storage_type, vault_identifier, vault_path)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, slug, label, secret_type, storage_type,
                          vault_identifier, vault_path, created_at, updated_at
                """,
                user_id,
                body.slug,
                body.label,
                value_enc,
                body.secret_type,
                body.storage_type,
                vault_identifier,
                vault_path,
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
        # Protection croisée (STANDARD Harpocrate §4) : un secret HARPOCRATE_API_KEY
        # référencé par un endpoint vault ne se supprime pas.
        endpoints = [
            r["name"]
            for r in await conn.fetch(
                "SELECT name FROM vault_wallet WHERE api_key_secret_ref = $1 ORDER BY name",
                secret_id,
            )
        ]
        if rows or webhooks or endpoints:
            labels = [r["label"] for r in rows]
            parts = []
            if labels:
                parts.append(f"{len(labels)} automate(s)")
            if webhooks:
                parts.append(f"{len(webhooks)} webhook(s)")
            if endpoints:
                parts.append(f"{len(endpoints)} endpoint(s) vault")
            raise HTTPException(
                409,
                {
                    "message": "secret utilisé par " + " et ".join(parts),
                    "automations": labels,
                    "webhooks": webhooks,
                    "endpoints": endpoints,
                },
            )
        result = await conn.execute(
            "DELETE FROM user_secret WHERE id = $1 AND owner_ref = $2",
            secret_id,
            user_id,
        )
    if result == "DELETE 0":
        raise HTTPException(404, "Secret introuvable.")


async def resolve_user_secret_value(
    pool: asyncpg.Pool,
    secret_id: uuid.UUID,
    enc_key: str,
    harpocrate_url: str | None = None,
) -> str | None:
    """Résout la valeur d'un secret utilisateur par son id (local ou vault).

    Utilisé par le résolveur `${secret://<uuid>}` (worker d'automate). La fabrique
    choisit le backend selon `storage_type` : local (déchiffrement Fernet) ou vault
    (endpoint → SDK Harpocrate). Résolution côté serveur — jamais renvoyée à l'API.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT storage_type, value_enc, vault_identifier, vault_path "
            "FROM user_secret WHERE id = $1",
            secret_id,
        )
    if row is None:
        return None
    from docflow.secrets.backends import create_backend

    backend = create_backend(
        row["storage_type"], pool=pool, enc_key=enc_key, harpocrate_url=harpocrate_url
    )
    return await backend.get(row)

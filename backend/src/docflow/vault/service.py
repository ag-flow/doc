from __future__ import annotations

import asyncio
import re
import secrets as _secrets
import uuid
from collections.abc import Iterable
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


async def delete_wallet(
    pool: asyncpg.Pool, owner_id: uuid.UUID, wallet_id: uuid.UUID
) -> None:
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
        if autos or producer:
            labels = [r["label"] for r in autos]
            parts = []
            if labels:
                parts.append(f"{len(labels)} automate(s)")
            if producer:
                parts.append("le producteur d'events")
            raise HTTPException(
                409,
                {
                    "message": "endpoint utilisé par " + " et ".join(parts),
                    "automations": labels,
                    "producer": bool(producer),
                },
            )
        await conn.execute(
            "DELETE FROM vault_wallet WHERE id = $1 AND owner_ref = $2", wallet_id, owner_id
        )


async def get_api_key(
    pool: asyncpg.Pool, name: str, enc_key: str
) -> tuple[str, str | None] | None:
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


# ── Secrets utilisateur ───────────────────────────────────────────────────────


async def list_secrets(
    pool: asyncpg.Pool,
    user_id: uuid.UUID,
    enc_key: str | None = None,
    secret_type: str | None = None,
) -> list[VaultSecretOut]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.slug, s.label, s.secret_type, s.created_at, s.updated_at,
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
    value_enc = encrypt_str(enc_key, body.value)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO user_secret (owner_ref, slug, label, value_enc, secret_type)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, slug, label, secret_type, created_at, updated_at
                """,
                user_id,
                body.slug,
                body.label,
                value_enc,
                body.secret_type,
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
            "SELECT value_enc FROM user_secret WHERE id = $1 AND owner_ref = $2 AND kind = 'hmac'",
            secret_id,
            user_id,
        )
    if row is None:
        raise HTTPException(404, "Secret HMAC introuvable.")
    return decrypt_str(enc_key, row["value_enc"])


# Référence à un secret utilisateur par id : ${secret://uuid} ou ${hmac://uuid}.
# Seuls ces deux schémas désignent un `user_secret` (propriété par utilisateur) ;
# ${vault://…} désigne un coffre d'instance (superadmin), hors isolation par user.
_OWNED_REF_RE = re.compile(r"^\$\{(?:secret|hmac)://([0-9a-fA-F-]{36})\}$")


async def assert_refs_owned(
    pool: asyncpg.Pool,
    refs: Iterable[str | None],
    owner_id: uuid.UUID,
) -> None:
    """Vérifie que toute référence ${secret://}/${hmac://} appartient à `owner_id`.

    Isolation stricte par propriétaire (STANDARD « Gestion des secrets » §1/§6) :
    on ne peut pas rattacher à un automate / webhook / config le secret d'un
    AUTRE utilisateur. Point d'application = l'écriture (là où l'identité existe),
    puisque la résolution ultérieure se fait côté worker, sans contexte requête.
    Les ${vault://…} (coffres d'instance) ne sont pas concernés. 403 si une
    référence pointe un secret inexistant ou d'un autre propriétaire.
    """
    seen: set[uuid.UUID] = set()
    for ref in refs:
        if not ref:
            continue
        m = _OWNED_REF_RE.match(ref.strip())
        if m:
            seen.add(uuid.UUID(m.group(1)))
    if not seen:
        return
    async with pool.acquire() as conn:
        owned = {
            r["id"]
            for r in await conn.fetch(
                "SELECT id FROM user_secret WHERE id = ANY($1::uuid[]) AND owner_ref = $2",
                list(seen),
                owner_id,
            )
        }
    foreign = seen - owned
    if foreign:
        raise HTTPException(
            status_code=403,
            detail=f"secret(s) non accessible(s) (autre propriétaire ou inexistant) : "
            f"{', '.join(str(s) for s in sorted(foreign))}",
        )


async def resolve_user_secret_value(
    pool: asyncpg.Pool, secret_id: uuid.UUID, enc_key: str
) -> str | None:
    """Résout la valeur d'un secret utilisateur par son id (tous kinds).

    Utilisé par le résolveur `${secret://<uuid>}` (worker d'automate) pour
    injecter une valeur secrète (ex. clé API externe) dans un header. Résolution
    par id global, côté serveur — la valeur n'est jamais renvoyée à l'API.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value_enc FROM user_secret WHERE id = $1", secret_id)
    if row is None:
        return None
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

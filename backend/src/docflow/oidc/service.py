from __future__ import annotations

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.auth.jwt import create_token
from docflow.config.settings import Settings
from docflow.oidc.verify import OidcVerifyError, exchange_code, fetch_discovery, verify_id_token
from docflow.schemas.auth import AuthUser
from docflow.schemas.oidc import OidcCallbackIn, OidcConfigOut, OidcConfigSet, OidcPublicConfig
from docflow.secrets.resolver import resolve
from docflow.secrets.secret import Secret

log = structlog.get_logger(__name__)

_SELECT = """
SELECT id, issuer, client_id, client_secret_ref, enabled, created_at, updated_at
FROM oidc_config LIMIT 1
"""


def _to_out(row: asyncpg.Record) -> OidcConfigOut:
    return OidcConfigOut(
        id=row["id"],
        issuer=row["issuer"],
        client_id=row["client_id"],
        enabled=row["enabled"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def get_oidc_config(pool: asyncpg.Pool) -> OidcConfigOut | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT)
    if row is None:
        return None
    return _to_out(row)


async def get_public_config(pool: asyncpg.Pool) -> OidcPublicConfig | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT)
    if row is None or not row["enabled"]:
        return None
    return OidcPublicConfig(
        issuer=row["issuer"],
        client_id=row["client_id"],
        enabled=row["enabled"],
    )


async def get_login_config(pool: asyncpg.Pool) -> OidcPublicConfig | None:
    """Config publique enrichie de l'authorization_endpoint découvert chez l'issuer.

    C'est ce que consomme la mire de connexion pour construire la redirection
    authorization-code. La découverte reste côté serveur (cache + garde SSRF).
    """
    public = await get_public_config(pool)
    if public is None:
        return None
    try:
        discovery = await fetch_discovery(public.issuer)
    except OidcVerifyError as exc:
        log.warning("oidc_discovery_failed", reason=str(exc))
        raise HTTPException(status_code=502, detail="issuer OIDC injoignable") from exc
    endpoint = str(discovery.get("authorization_endpoint", ""))
    if not endpoint:
        raise HTTPException(
            status_code=502, detail="authorization_endpoint absent du document de découverte"
        )
    return public.model_copy(update={"authorization_endpoint": endpoint})


async def set_oidc_config(pool: asyncpg.Pool, data: OidcConfigSet) -> OidcConfigOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow("SELECT id FROM oidc_config LIMIT 1")
            if existing is None:
                row = await conn.fetchrow(
                    """
                    INSERT INTO oidc_config (issuer, client_id, client_secret_ref, enabled)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, issuer, client_id, client_secret_ref,
                              enabled, created_at, updated_at
                    """,
                    data.issuer,
                    data.client_id,
                    data.client_secret_ref,
                    data.enabled,
                )
            else:
                row = await conn.fetchrow(
                    """
                    UPDATE oidc_config
                    SET issuer = $1, client_id = $2, client_secret_ref = $3,
                        enabled = $4, updated_at = now()
                    WHERE id = $5
                    RETURNING id, issuer, client_id, client_secret_ref,
                              enabled, created_at, updated_at
                    """,
                    data.issuer,
                    data.client_id,
                    data.client_secret_ref,
                    data.enabled,
                    existing["id"],
                )
    assert row is not None
    return _to_out(row)


async def handle_oidc_callback(pool: asyncpg.Pool, settings: Settings, body: OidcCallbackIn) -> str:
    """Flow authorization-code : échange le code, vérifie l'id_token, émet un JWT docflow.

    Aucun claim n'est accepté sans vérification serveur de la signature de
    l'id_token contre le JWKS de l'issuer configuré (AUTH-01).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SELECT)
    if row is None or not row["enabled"]:
        raise HTTPException(status_code=403, detail="OIDC non activé")
    issuer: str = row["issuer"]
    client_id: str = row["client_id"]

    enc = settings.encryption_key
    client_secret = await resolve(
        Secret(row["client_secret_ref"]),
        harpocrate_url=settings.harpocrate_url,
        pool=pool,
        enc_key=enc.reveal() if enc is not None else None,
    )
    try:
        id_token = await exchange_code(
            issuer=issuer,
            code=body.code,
            redirect_uri=body.redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
        )
        claims = await verify_id_token(
            id_token, issuer=issuer, client_id=client_id, nonce=body.nonce
        )
    except OidcVerifyError as exc:
        # Le message d'OidcVerifyError ne contient ni token, ni claims, ni secret.
        log.warning("oidc_callback_rejected", reason=str(exc))
        raise HTTPException(status_code=401, detail="échec de vérification OIDC") from exc
    return await issue_token_for_verified_claims(pool, settings.jwt_secret.reveal(), claims)


async def issue_token_for_verified_claims(
    pool: asyncpg.Pool, jwt_secret: str, id_token_claims: dict[str, object]
) -> str:
    """Provisionne ou lie l'app_user depuis des claims OIDC **déjà vérifiés**.

    Ne jamais appeler avec des claims non vérifiés : la vérification de
    signature/iss/aud/exp est faite en amont par `handle_oidc_callback`.
    """
    email = str(id_token_claims.get("email", ""))
    sub = str(id_token_claims.get("sub", ""))
    name = str(id_token_claims.get("name", email))
    if not email or not sub:
        raise HTTPException(status_code=422, detail="claims OIDC manquants (email/sub)")
    # email_verified peut être un booléen (standard OIDC) ou une chaîne "true" selon l'IdP.
    email_verified_raw = id_token_claims.get("email_verified")
    email_verified = email_verified_raw is True or str(email_verified_raw).lower() == "true"

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Vérifier que OIDC est activé
            enabled_raw: bool | None = await conn.fetchval(
                "SELECT enabled FROM oidc_config LIMIT 1"
            )
            enabled: bool = bool(enabled_raw)
            if not enabled:
                raise HTTPException(status_code=403, detail="OIDC non activé")

            # Chercher par oidc_subject d'abord, puis par email
            user_row = await conn.fetchrow(
                "SELECT id, email, label, is_admin, validated, disabled "
                "FROM app_user WHERE oidc_subject = $1",
                sub,
            )
            if user_row is None:
                user_row = await conn.fetchrow(
                    "SELECT id, email, label, is_admin, validated, disabled "
                    "FROM app_user WHERE email = $1",
                    email,
                )
                if user_row is not None:
                    # Ne lier un compte existant par email que si l'IdP a vérifié cet email,
                    # sinon un sub attaquant portant l'email d'un compte local (admin) en
                    # prendrait le contrôle (account takeover). Cf. AUTH-02.
                    if not email_verified:
                        raise HTTPException(
                            status_code=403,
                            detail="liaison OIDC refusée: email non vérifié par l'IdP",
                        )
                    await conn.execute(
                        "UPDATE app_user SET oidc_subject = $1, source = 'oidc' WHERE id = $2",
                        sub,
                        user_row["id"],
                    )
                else:
                    # Nouveau compte OIDC : non admin, non validé
                    user_row = await conn.fetchrow(
                        """
                        INSERT INTO app_user
                            (email, label, oidc_subject, is_admin, validated, source)
                        VALUES ($1, $2, $3, false, false, 'oidc')
                        RETURNING id, email, label, is_admin, validated, disabled
                        """,
                        email,
                        name,
                        sub,
                    )
    assert user_row is not None
    if user_row["disabled"]:
        raise HTTPException(status_code=403, detail="compte désactivé")
    if not user_row["validated"]:
        raise HTTPException(status_code=403, detail="PendingValidation")

    user = AuthUser(
        id=user_row["id"],
        email=user_row["email"],
        label=user_row["label"],
        is_admin=user_row["is_admin"],
        validated=user_row["validated"],
        disabled=user_row["disabled"],
    )
    return create_token(user, jwt_secret)


async def resolve_client_secret(
    pool: asyncpg.Pool,
    harpocrate_url: str | None,
    enc_key: str | None = None,
) -> str:
    """Déballe le client_secret_ref au point d'usage uniquement."""
    async with pool.acquire() as conn:
        ref: str | None = await conn.fetchval(
            "SELECT client_secret_ref FROM oidc_config WHERE enabled = true LIMIT 1"
        )
    if ref is None:
        raise HTTPException(status_code=503, detail="OIDC non configuré")
    return await resolve(Secret(ref), harpocrate_url=harpocrate_url, pool=pool, enc_key=enc_key)

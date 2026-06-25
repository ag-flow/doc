from __future__ import annotations

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.auth.jwt import create_token
from docflow.schemas.auth import AuthUser
from docflow.schemas.oidc import OidcConfigOut, OidcConfigSet, OidcPublicConfig
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
                    data.issuer, data.client_id, data.client_secret_ref, data.enabled,
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
                    data.issuer, data.client_id, data.client_secret_ref, data.enabled,
                    existing["id"],
                )
    assert row is not None
    return _to_out(row)


async def handle_oidc_callback(
    pool: asyncpg.Pool, jwt_secret: str, id_token_claims: dict[str, object]
) -> str:
    """Provisionne ou lie l'admin_user depuis les claims OIDC, retourne un JWT docflow."""
    email = str(id_token_claims.get("email", ""))
    sub = str(id_token_claims.get("sub", ""))
    name = str(id_token_claims.get("name", email))
    if not email or not sub:
        raise HTTPException(status_code=422, detail="claims OIDC manquants (email/sub)")

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
                "SELECT id, email, label, is_superadmin, disabled, password_hash "
                "FROM admin_user WHERE oidc_subject = $1",
                sub,
            )
            if user_row is None:
                user_row = await conn.fetchrow(
                    "SELECT id, email, label, is_superadmin, disabled, password_hash "
                    "FROM admin_user WHERE email = $1",
                    email,
                )
                if user_row is not None:
                    # Lier le compte existant : remplir oidc_subject, préserver password_hash
                    await conn.execute(
                        "UPDATE admin_user SET oidc_subject = $1 WHERE id = $2",
                        sub, user_row["id"],
                    )
                else:
                    # Provisionner un nouveau compte (sans password_hash)
                    user_row = await conn.fetchrow(
                        """
                        INSERT INTO admin_user (email, label, oidc_subject, is_superadmin)
                        VALUES ($1, $2, $3, false)
                        RETURNING id, email, label, is_superadmin, disabled, password_hash
                        """,
                        email, name, sub,
                    )
    assert user_row is not None
    if user_row["disabled"]:
        raise HTTPException(status_code=403, detail="compte désactivé")

    user = AuthUser(
        id=user_row["id"],
        email=user_row["email"],
        label=user_row["label"],
        is_superadmin=user_row["is_superadmin"],
        disabled=user_row["disabled"],
    )
    return create_token(user, jwt_secret)


async def resolve_client_secret(pool: asyncpg.Pool, harpocrate_url: str | None) -> str:
    """Déballe le client_secret_ref au point d'usage uniquement."""
    async with pool.acquire() as conn:
        ref: str | None = await conn.fetchval(
            "SELECT client_secret_ref FROM oidc_config WHERE enabled = true LIMIT 1"
        )
    if ref is None:
        raise HTTPException(status_code=503, detail="OIDC non configuré")
    return await resolve(Secret(ref), harpocrate_url=harpocrate_url)

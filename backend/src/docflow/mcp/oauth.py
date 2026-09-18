"""Surface MCP en serveur de ressources OAuth 2.1 (RFC 9728).

docflow n'émet PAS de jeton (pas de serveur OAuth maison) : il publie ici quel
serveur d'autorisation fait foi (le realm OIDC configuré) et valide les jetons
d'accès entrants contre son JWKS. Repris de la référence a2a
(routers/mcp_gateway_metadata.py + auth/inbound_agent_auth.py).
"""

from __future__ import annotations

import asyncpg
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from docflow.config.base_url import effective_base_url
from docflow.config.settings import Settings
from docflow.oidc.verify import OidcVerifyError, verify_access_token
from docflow.schemas.auth import AuthUser

log = structlog.get_logger(__name__)

# Chemin des métadonnées de ressource protégée (public par construction : un
# client doit pouvoir le lire AVANT d'être authentifié — c'est tout son objet).
PRM_PATH = "/.well-known/oauth-protected-resource"

router = APIRouter(tags=["mcp-oauth"])


class ProtectedResourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource: str
    authorization_servers: list[str]
    bearer_methods_supported: list[str]
    scopes_supported: list[str]


def www_authenticate(settings: Settings | None) -> str:
    """En-tête WWW-Authenticate désignant les métadonnées de ressource : c'est ce
    qui permet à un client MCP standard de découvrir où s'authentifier."""
    base = (effective_base_url(settings) or "").rstrip("/")
    return f'Bearer resource_metadata="{base}{PRM_PATH}"'


@router.get(PRM_PATH, response_model=ProtectedResourceMetadata)
async def protected_resource_metadata(request: Request) -> ProtectedResourceMetadata:
    """Document de métadonnées de ressource protégée — PUBLIC (aucune auth)."""
    settings = request.app.state.settings
    pool: asyncpg.Pool = request.app.state.pool
    # L'émetteur annoncé est celui RÉELLEMENT configuré (page OIDC), pas une
    # constante : une instance sans OIDC n'annonce aucun serveur d'autorisation.
    async with pool.acquire() as conn:
        issuer: str | None = await conn.fetchval(
            "SELECT issuer FROM oidc_config WHERE enabled = true LIMIT 1"
        )
    base = (effective_base_url(settings) or "").rstrip("/")
    return ProtectedResourceMetadata(
        resource=f"{base}/api/mcp",
        authorization_servers=[issuer] if issuer else [],
        bearer_methods_supported=["header"],
        scopes_supported=[settings.oauth2_audience],
    )


_SELECT_BY_PIN = (
    "SELECT id, email, label, is_admin, validated, disabled "
    "FROM app_user WHERE oidc_issuer = $1 AND oidc_subject = $2"
)


async def resolve_idp_bearer(
    pool: asyncpg.Pool, settings: Settings, token: str
) -> AuthUser | None:
    """Résout un jeton d'accès IdP (Bearer JWT) en app_user, ou None si le jeton
    n'est pas vérifiable / mauvaise audience (→ 401 côté appelant).

    Lève HTTPException(403) quand le jeton est VALIDE mais ne correspond à aucun
    compte docflow utilisable (jamais connecté en OIDC, désactivé, non validé) :
    l'identité est prouvée, c'est l'autorisation applicative qui manque.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT issuer, enabled FROM oidc_config LIMIT 1"
        )
    if row is None or not row["enabled"]:
        return None  # pas d'IdP configuré → aucun jeton d'accès à valider
    issuer: str = row["issuer"]

    try:
        claims = await verify_access_token(
            token, issuer=issuer, audience=settings.oauth2_audience
        )
    except OidcVerifyError as exc:
        log.warning("mcp_bearer_rejected", reason=str(exc), exc_info=True)
        return None

    sub = str(claims.get("sub", ""))
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(_SELECT_BY_PIN, issuer, sub)
    if user_row is None:
        raise HTTPException(status_code=403, detail="aucun compte docflow pour cette identité OIDC")
    if user_row["disabled"]:
        raise HTTPException(status_code=403, detail="compte désactivé")
    if not user_row["validated"]:
        raise HTTPException(status_code=403, detail="PendingValidation")
    return AuthUser(
        id=user_row["id"],
        email=user_row["email"],
        label=user_row["label"],
        is_admin=user_row["is_admin"],
        validated=user_row["validated"],
        disabled=user_row["disabled"],
    )

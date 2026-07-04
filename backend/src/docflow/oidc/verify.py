"""Vérification serveur du flow OIDC (AUTH-01).

Le backend ne fait JAMAIS confiance à des claims postés par le client : il
échange le `code` au token endpoint de l'issuer configuré, puis vérifie
lui-même l'id_token — signature contre le JWKS de l'issuer (découvert via
`.well-known/openid-configuration`), `iss`, `aud` (= client_id), `exp` et,
si le client l'a fourni, `nonce`.
"""

from __future__ import annotations

import time
from typing import Any, cast

import httpx
import structlog
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet, KeySetSerialization

from docflow.net.ssrf import SSRFError, validate_public_url

log = structlog.get_logger(__name__)

_TIMEOUT = 10.0
_CACHE_TTL = 300.0  # secondes — discovery et JWKS

# Algorithmes asymétriques uniquement : accepter HS* ouvrirait une confusion
# de clé (id_token forgé signé avec une valeur devinable côté client).
_ALLOWED_ALGS = [
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
    "ES256",
    "ES384",
    "ES512",
]


class OidcVerifyError(Exception):
    """Échange ou vérification OIDC refusé — aucun token docflow ne doit être émis."""


# Caches module-level : {clé: (expire_à_monotonic, valeur)}
_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_jwks_cache: dict[str, tuple[float, KeySet]] = {}


async def _fetch_json(url: str) -> dict[str, Any]:
    """GET JSON avec garde SSRF, timeout court et sans suivi de redirection."""
    try:
        await validate_public_url(url)
    except SSRFError as exc:
        raise OidcVerifyError(f"URL OIDC refusée par la politique anti-SSRF: {exc}") from exc
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, follow_redirects=False)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise OidcVerifyError(f"issuer OIDC injoignable ({type(exc).__name__})") from exc
    except ValueError as exc:
        raise OidcVerifyError("réponse OIDC non-JSON") from exc
    if not isinstance(data, dict):
        raise OidcVerifyError("réponse OIDC inattendue (objet JSON requis)")
    return data


async def fetch_discovery(issuer: str) -> dict[str, Any]:
    """Récupère (avec cache) le document de découverte OIDC de l'issuer configuré."""
    cached = _discovery_cache.get(issuer)
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    doc = await _fetch_json(url)
    # OIDC Discovery §4.3 : l'issuer annoncé doit correspondre à celui configuré.
    announced = str(doc.get("issuer", ""))
    if announced.rstrip("/") != issuer.rstrip("/"):
        raise OidcVerifyError("issuer du document de découverte différent de l'issuer configuré")
    _discovery_cache[issuer] = (time.monotonic() + _CACHE_TTL, doc)
    return doc


async def fetch_jwks(jwks_uri: str, *, force_refresh: bool = False) -> KeySet:
    """Récupère (avec cache) le JWKS de l'issuer ; `force_refresh` en cas de rotation."""
    if not force_refresh:
        cached = _jwks_cache.get(jwks_uri)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]
    data = await _fetch_json(jwks_uri)
    if not isinstance(data.get("keys"), list):
        raise OidcVerifyError("JWKS de l'issuer invalide (champ keys absent)")
    try:
        keyset = KeySet.import_key_set(cast(KeySetSerialization, data))
    except (JoseError, KeyError, ValueError) as exc:
        raise OidcVerifyError("JWKS de l'issuer invalide") from exc
    _jwks_cache[jwks_uri] = (time.monotonic() + _CACHE_TTL, keyset)
    return keyset


def validate_id_token_claims(
    id_token: str,
    keyset: KeySet,
    *,
    issuer: str,
    client_id: str,
    nonce: str | None = None,
    leeway: int = 60,
) -> dict[str, Any]:
    """Vérifie signature + iss + aud + exp (+ nonce) ; retourne les claims vérifiés.

    Lève `OidcVerifyError` (et uniquement elle) sur tout défaut. Le message ne
    contient jamais le token ni les claims.
    """
    try:
        token = jwt.decode(id_token, keyset, algorithms=_ALLOWED_ALGS)
        options: dict[str, Any] = {
            "iss": {"essential": True, "value": issuer},
            "aud": {"essential": True, "value": client_id},
            "exp": {"essential": True},
            "sub": {"essential": True},
        }
        if nonce is not None:
            options["nonce"] = {"essential": True, "value": nonce}
        registry = jwt.JWTClaimsRegistry(leeway=leeway, **options)
        registry.validate(token.claims)
    except JoseError as exc:
        raise OidcVerifyError(f"id_token rejeté ({type(exc).__name__})") from exc
    except ValueError as exc:
        raise OidcVerifyError("id_token malformé") from exc
    claims: dict[str, Any] = token.claims
    # OIDC Core §3.1.3.7 : avec plusieurs audiences, azp doit être présent ;
    # s'il est présent, il doit valoir notre client_id.
    aud = claims.get("aud")
    azp = claims.get("azp")
    if isinstance(aud, list) and len(aud) > 1 and azp is None:
        raise OidcVerifyError("id_token multi-audience sans claim azp")
    if azp is not None and azp != client_id:
        raise OidcVerifyError("claim azp différent du client_id")
    return claims


async def verify_id_token(
    id_token: str, *, issuer: str, client_id: str, nonce: str | None = None
) -> dict[str, Any]:
    """Vérifie un id_token contre le JWKS de l'issuer configuré (rotation gérée)."""
    discovery = await fetch_discovery(issuer)
    jwks_uri = str(discovery.get("jwks_uri", ""))
    if not jwks_uri:
        raise OidcVerifyError("jwks_uri absent du document de découverte")
    keyset = await fetch_jwks(jwks_uri)
    try:
        return validate_id_token_claims(
            id_token, keyset, issuer=issuer, client_id=client_id, nonce=nonce
        )
    except OidcVerifyError as first_error:
        # kid inconnu → une rotation de clés a pu avoir lieu : re-fetch une fois.
        if not isinstance(first_error.__cause__, InvalidKeyIdError):
            raise
        keyset = await fetch_jwks(jwks_uri, force_refresh=True)
        return validate_id_token_claims(
            id_token, keyset, issuer=issuer, client_id=client_id, nonce=nonce
        )


async def exchange_code(
    *, issuer: str, code: str, redirect_uri: str, client_id: str, client_secret: str
) -> str:
    """Échange le code d'autorisation au token endpoint ; retourne l'id_token brut.

    Authentification client `client_secret_basic` ; le secret n'apparaît ni en
    log ni dans les messages d'erreur.
    """
    discovery = await fetch_discovery(issuer)
    token_endpoint = str(discovery.get("token_endpoint", ""))
    if not token_endpoint:
        raise OidcVerifyError("token_endpoint absent du document de découverte")
    try:
        await validate_public_url(token_endpoint)
    except SSRFError as exc:
        raise OidcVerifyError(f"token_endpoint refusé par la politique anti-SSRF: {exc}") from exc
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                auth=(client_id, client_secret),
                follow_redirects=False,
            )
    except httpx.HTTPError as exc:
        raise OidcVerifyError(f"token endpoint injoignable ({type(exc).__name__})") from exc
    if resp.status_code != 200:
        log.warning("oidc_code_exchange_failed", status=resp.status_code)
        raise OidcVerifyError("échange du code refusé par l'issuer")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise OidcVerifyError("réponse du token endpoint non-JSON") from exc
    id_token = payload.get("id_token") if isinstance(payload, dict) else None
    if not isinstance(id_token, str) or not id_token:
        raise OidcVerifyError("id_token absent de la réponse du token endpoint")
    return id_token

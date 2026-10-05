"""Surface MCP en serveur de ressources OAuth 2.1 (RFC 9728).

Métadonnées de ressource protégée, WWW-Authenticate, validation d'audience d'un
jeton d'accès entrant, résolution en app_user par (issuer, sub).
"""

from __future__ import annotations

import time
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from docflow.app import app
from docflow.oidc.verify import OidcVerifyError, validate_access_token_claims

_ISSUER = "https://idp.example.com/realms/test"
_AUDIENCE = "docflow-mcp"
_KID = "kid-mcp-1"


@pytest.fixture(scope="module")
def idp_key() -> RSAKey:
    return RSAKey.generate_key(2048, {"kid": _KID, "alg": "RS256"})


@pytest.fixture(scope="module")
def idp_jwks(idp_key: RSAKey) -> KeySet:
    return KeySet.import_key_set(KeySet([idp_key]).as_dict(private=False))


def _access_token(key: RSAKey, extra: dict[str, Any] | None = None) -> str:
    claims: dict[str, Any] = {
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "sub": "kc-sub-1",
        "exp": int(time.time()) + 300,
    }
    claims.update(extra or {})
    return jwt.encode({"alg": "RS256", "kid": _KID}, claims, key)


# ── Unité : validation d'audience du jeton d'accès ───────────────────────────


def test_access_token_bonne_audience(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    claims = validate_access_token_claims(
        _access_token(idp_key), idp_jwks, issuer=_ISSUER, audience=_AUDIENCE
    )
    assert claims["sub"] == "kc-sub-1"


def test_access_token_mauvaise_audience_refuse(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    """AC : un jeton émis pour un AUTRE serveur MCP de la stack est refusé."""
    tok = _access_token(idp_key, {"aud": "autre-serveur-mcp"})
    with pytest.raises(OidcVerifyError, match="audience"):
        validate_access_token_claims(tok, idp_jwks, issuer=_ISSUER, audience=_AUDIENCE)


def test_access_token_audience_liste_contient(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    """aud multi-valeur : accepté si notre ressource en fait partie."""
    tok = _access_token(idp_key, {"aud": ["autre", _AUDIENCE]})
    claims = validate_access_token_claims(tok, idp_jwks, issuer=_ISSUER, audience=_AUDIENCE)
    assert claims["sub"] == "kc-sub-1"


def test_access_token_mauvais_issuer_refuse(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    tok = _access_token(idp_key, {"iss": "https://evil.example.com"})
    with pytest.raises(OidcVerifyError):
        validate_access_token_claims(tok, idp_jwks, issuer=_ISSUER, audience=_AUDIENCE)


def test_access_token_expire_refuse(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    tok = _access_token(idp_key, {"exp": int(time.time()) - 3600})
    with pytest.raises(OidcVerifyError):
        validate_access_token_claims(tok, idp_jwks, issuer=_ISSUER, audience=_AUDIENCE)


# ── PRM public + WWW-Authenticate ────────────────────────────────────────────


def test_mcp_401_porte_www_authenticate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un accès MCP sans jeton reçoit 401 + WWW-Authenticate désignant les
    métadonnées de ressource (découverte du client MCP standard)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalide/x")
    monkeypatch.setenv("JWT_SECRET", "s" * 64)
    client = TestClient(app)  # sans lifespan : le 401 ne touche pas la DB
    r = client.get("/api/mcp/sse")
    assert r.status_code == 401
    assert "resource_metadata" in r.headers.get("WWW-Authenticate", "")


async def test_protected_resource_metadata_public(
    db_pool: asyncpg.Pool,
    test_schema_url: str,
    clean_admin_users: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le document PRM est servi sans auth et annonce l'émetteur configuré."""
    await _enable_oidc(db_pool)
    # Le lifespan du client instancie Settings() : mêmes DSN/schéma que db_pool.
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    with TestClient(app) as client:  # lifespan : pool réel sur le schéma de test
        r = client.get("/.well-known/oauth-protected-resource")
    assert r.status_code == 200
    body = r.json()
    assert body["authorization_servers"] == [_ISSUER]
    assert body["scopes_supported"] == ["docflow-mcp"]
    assert body["resource"].endswith("/api/mcp")


# ── Résolution du jeton IdP en app_user ──────────────────────────────────────


async def _enable_oidc(db_pool: asyncpg.Pool) -> None:
    from docflow.oidc import service as oidc_svc
    from docflow.schemas.oidc import OidcConfigSet

    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer=_ISSUER, client_id="docflow", client_secret_ref="inline", enabled=True
        ),
    )


class _Settings:
    oauth2_audience = _AUDIENCE


async def test_resolve_idp_bearer_sub_epingle(
    db_pool: asyncpg.Pool, clean_admin_users: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from docflow.mcp import oauth

    await _enable_oidc(db_pool)
    await db_pool.execute(
        "INSERT INTO app_user (email, label, is_admin, validated, oidc_issuer, oidc_subject) "
        "VALUES ('u@ex.com', 'U', false, true, $1, 'kc-sub-1')",
        _ISSUER,
    )

    async def _fake_verify(token: str, *, issuer: str, audience: str) -> dict[str, Any]:
        assert audience == _AUDIENCE
        return {"sub": "kc-sub-1", "iss": issuer}

    monkeypatch.setattr(oauth, "verify_access_token", _fake_verify)
    user = await oauth.resolve_idp_bearer(db_pool, _Settings(), "tok")  # type: ignore[arg-type]
    assert user is not None
    assert user.email == "u@ex.com"


async def test_resolve_idp_bearer_audience_invalide_rend_none(
    db_pool: asyncpg.Pool, clean_admin_users: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from docflow.mcp import oauth

    await _enable_oidc(db_pool)

    async def _fake_verify(token: str, *, issuer: str, audience: str) -> dict[str, Any]:
        raise OidcVerifyError("audience du jeton différente de la ressource docflow")

    monkeypatch.setattr(oauth, "verify_access_token", _fake_verify)
    assert await oauth.resolve_idp_bearer(db_pool, _Settings(), "tok") is None  # type: ignore[arg-type]


async def test_resolve_idp_bearer_sub_inconnu_403(
    db_pool: asyncpg.Pool, clean_admin_users: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi import HTTPException

    from docflow.mcp import oauth

    await _enable_oidc(db_pool)

    async def _fake_verify(token: str, *, issuer: str, audience: str) -> dict[str, Any]:
        return {"sub": "sub-jamais-vu", "iss": issuer}

    monkeypatch.setattr(oauth, "verify_access_token", _fake_verify)
    with pytest.raises(HTTPException) as exc:
        await oauth.resolve_idp_bearer(db_pool, _Settings(), "tok")  # type: ignore[arg-type]
    assert exc.value.status_code == 403


async def test_resolve_idp_bearer_oidc_desactive_rend_none(
    db_pool: asyncpg.Pool, clean_admin_users: None
) -> None:
    """Sans IdP configuré/activé, aucun jeton d'accès n'est à valider."""
    from docflow.mcp import oauth

    assert await oauth.resolve_idp_bearer(db_pool, _Settings(), "tok") is None  # type: ignore[arg-type]

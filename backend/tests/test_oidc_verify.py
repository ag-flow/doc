"""Tests unitaires (sans DB) de la vérification serveur de l'id_token — AUTH-01.

Un id_token forgé (mauvaise signature, iss/aud incorrects, expiré, alg=none…)
ne doit JAMAIS produire de claims vérifiés.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import pytest
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from docflow.oidc import verify as oidc_verify
from docflow.oidc.verify import (
    OidcVerifyError,
    validate_id_token_claims,
    verify_id_token,
)

_ISSUER = "https://idp.example.com/realms/test"
_CLIENT_ID = "docflow"
_KID = "kid-1"


@pytest.fixture(scope="module")
def idp_key() -> RSAKey:
    return RSAKey.generate_key(2048, {"kid": _KID, "alg": "RS256"})


@pytest.fixture(scope="module")
def idp_jwks(idp_key: RSAKey) -> KeySet:
    """JWKS public tel que servi par l'issuer (clés publiques uniquement)."""
    return KeySet.import_key_set(KeySet([idp_key]).as_dict(private=False))


def _sign(
    key: RSAKey,
    extra: dict[str, Any] | None = None,
    *,
    kid: str = _KID,
    drop: frozenset[str] = frozenset(),
) -> str:
    claims: dict[str, Any] = {
        "iss": _ISSUER,
        "aud": _CLIENT_ID,
        "sub": "sub-1",
        "email": "user@example.com",
        "email_verified": True,
        "exp": int(time.time()) + 300,
    }
    claims.update(extra or {})
    for name in drop:
        claims.pop(name, None)
    return jwt.encode({"alg": "RS256", "kid": kid}, claims, key)


def test_valid_id_token_returns_claims(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    claims = validate_id_token_claims(
        _sign(idp_key), idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID
    )
    assert claims["sub"] == "sub-1"
    assert claims["email"] == "user@example.com"


def test_bad_signature_rejected(idp_jwks: KeySet) -> None:
    """Token signé par une AUTRE clé portant le même kid → rejet."""
    attacker_key = RSAKey.generate_key(2048, {"kid": _KID, "alg": "RS256"})
    token = _sign(attacker_key)
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims(token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)


def test_wrong_issuer_rejected(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    token = _sign(idp_key, {"iss": "https://evil.example.com"})
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims(token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)


def test_wrong_audience_rejected(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    token = _sign(idp_key, {"aud": "other-client"})
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims(token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)


def test_expired_token_rejected(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    token = _sign(idp_key, {"exp": int(time.time()) - 3600})
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims(token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)


def test_missing_exp_rejected(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    token = _sign(idp_key, drop=frozenset({"exp"}))
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims(token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)


def test_missing_sub_rejected(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    token = _sign(idp_key, drop=frozenset({"sub"}))
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims(token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)


def test_alg_none_rejected(idp_jwks: KeySet) -> None:
    """Un token forgé alg=none (non signé) ne doit jamais passer."""

    def b64(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    payload = {
        "iss": _ISSUER,
        "aud": _CLIENT_ID,
        "sub": "sub-1",
        "exp": int(time.time()) + 300,
    }
    forged = f"{b64({'alg': 'none'})}.{b64(payload)}."
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims(forged, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)


def test_garbage_token_rejected(idp_jwks: KeySet) -> None:
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims("not-a-jwt", idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)


def test_nonce_mismatch_rejected(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    token = _sign(idp_key, {"nonce": "nonce-A"})
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims(
            token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID, nonce="nonce-B"
        )


def test_nonce_match_accepted(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    token = _sign(idp_key, {"nonce": "nonce-A"})
    claims = validate_id_token_claims(
        token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID, nonce="nonce-A"
    )
    assert claims["nonce"] == "nonce-A"


def test_multi_audience_without_azp_rejected(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    token = _sign(idp_key, {"aud": [_CLIENT_ID, "other"]})
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims(token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)


def test_multi_audience_with_matching_azp_accepted(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    token = _sign(idp_key, {"aud": [_CLIENT_ID, "other"], "azp": _CLIENT_ID})
    claims = validate_id_token_claims(token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)
    assert claims["azp"] == _CLIENT_ID


def test_azp_mismatch_rejected(idp_key: RSAKey, idp_jwks: KeySet) -> None:
    token = _sign(idp_key, {"azp": "other-client"})
    with pytest.raises(OidcVerifyError):
        validate_id_token_claims(token, idp_jwks, issuer=_ISSUER, client_id=_CLIENT_ID)


# ── verify_id_token : discovery/JWKS mockés, rotation de clés ─────────────────


async def test_verify_id_token_nominal(
    idp_key: RSAKey, idp_jwks: KeySet, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_discovery(issuer: str) -> dict[str, Any]:
        assert issuer == _ISSUER
        return {"issuer": _ISSUER, "jwks_uri": f"{_ISSUER}/certs"}

    async def fake_jwks(jwks_uri: str, *, force_refresh: bool = False) -> KeySet:
        return idp_jwks

    monkeypatch.setattr(oidc_verify, "fetch_discovery", fake_discovery)
    monkeypatch.setattr(oidc_verify, "fetch_jwks", fake_jwks)
    claims = await verify_id_token(_sign(idp_key), issuer=_ISSUER, client_id=_CLIENT_ID)
    assert claims["sub"] == "sub-1"


async def test_verify_id_token_refreshes_jwks_on_unknown_kid(
    idp_key: RSAKey, idp_jwks: KeySet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """kid absent du JWKS en cache → un unique re-fetch (rotation de clés)."""
    stale_key = RSAKey.generate_key(2048, {"kid": "kid-old", "alg": "RS256"})
    stale_jwks = KeySet.import_key_set(KeySet([stale_key]).as_dict(private=False))
    calls: list[bool] = []

    async def fake_discovery(issuer: str) -> dict[str, Any]:
        return {"issuer": _ISSUER, "jwks_uri": f"{_ISSUER}/certs"}

    async def fake_jwks(jwks_uri: str, *, force_refresh: bool = False) -> KeySet:
        calls.append(force_refresh)
        return idp_jwks if force_refresh else stale_jwks

    monkeypatch.setattr(oidc_verify, "fetch_discovery", fake_discovery)
    monkeypatch.setattr(oidc_verify, "fetch_jwks", fake_jwks)
    claims = await verify_id_token(_sign(idp_key), issuer=_ISSUER, client_id=_CLIENT_ID)
    assert claims["sub"] == "sub-1"
    assert calls == [False, True]


async def test_verify_id_token_no_refresh_on_bad_signature(
    idp_jwks: KeySet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mauvaise signature (kid connu) → rejet direct, PAS de re-fetch du JWKS."""
    attacker_key = RSAKey.generate_key(2048, {"kid": _KID, "alg": "RS256"})
    calls: list[bool] = []

    async def fake_discovery(issuer: str) -> dict[str, Any]:
        return {"issuer": _ISSUER, "jwks_uri": f"{_ISSUER}/certs"}

    async def fake_jwks(jwks_uri: str, *, force_refresh: bool = False) -> KeySet:
        calls.append(force_refresh)
        return idp_jwks

    monkeypatch.setattr(oidc_verify, "fetch_discovery", fake_discovery)
    monkeypatch.setattr(oidc_verify, "fetch_jwks", fake_jwks)
    with pytest.raises(OidcVerifyError):
        await verify_id_token(_sign(attacker_key), issuer=_ISSUER, client_id=_CLIENT_ID)
    assert calls == [False]

from __future__ import annotations

import time
import uuid

from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import OctKey

from docflow.schemas.auth import AuthUser

_ALG = {"alg": "HS256"}
_TTL = 8 * 3600  # 8 heures en secondes
_CLAIMS_REGISTRY = jwt.JWTClaimsRegistry()


def create_token(user: AuthUser, secret: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "is_superadmin": user.is_superadmin,
        "iat": now,
        "exp": now + _TTL,
    }
    key = OctKey.import_key(secret)
    return jwt.encode(_ALG, payload, key)


def decode_token(token: str, secret: str) -> dict[str, object]:
    """Decode and validate a JWT. Raises ValueError on any failure."""
    try:
        key = OctKey.import_key(secret)
        decoded = jwt.decode(token, key)
        _CLAIMS_REGISTRY.validate(decoded.claims)
        return dict(decoded.claims)
    except JoseError as exc:
        raise ValueError(f"token invalide : {exc}") from exc


def user_id_from_claims(claims: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(claims["sub"]))

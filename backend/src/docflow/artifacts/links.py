from __future__ import annotations

import hashlib
import hmac
import time
import uuid

# Séparation de domaine : la clé JWT sert aussi à signer ces liens, le
# préfixe garantit qu'une signature de lien n'est jamais un JWT valide
# (et réciproquement).
_DOMAIN = "docflow-artifact-link"


def _sign(ws_slug: str, artifact_id: uuid.UUID, expires_at: int, secret: str) -> str:
    message = f"{_DOMAIN}:{ws_slug}:{artifact_id}:{expires_at}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def build_download_query(
    ws_slug: str, artifact_id: uuid.UUID, *, ttl_seconds: int, secret: str
) -> str:
    """Construit la query string signée (`exp=...&sig=...`) d'un lien de téléchargement."""
    expires_at = int(time.time()) + ttl_seconds
    sig = _sign(ws_slug, artifact_id, expires_at, secret)
    return f"exp={expires_at}&sig={sig}"


def verify_download_sig(
    ws_slug: str, artifact_id: uuid.UUID, expires_at: int, sig: str, *, secret: str
) -> bool:
    """Vérifie signature ET expiration. Comparaison en temps constant."""
    if expires_at < int(time.time()):
        return False
    expected = _sign(ws_slug, artifact_id, expires_at, secret)
    return hmac.compare_digest(expected, sig)

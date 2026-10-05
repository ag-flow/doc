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


# ── Liens de preview de maquette (révision-conscients) ───────────────────────
# Domaine distinct des liens de téléchargement : un lien de preview est lié à
# UNE révision précise (les artefacts de maquette étant mutables, un lien mis en
# cache ne doit jamais rendre une révision périmée). Servi UNIQUEMENT sur
# l'origine de preview dédiée (cf. preview_router).
_PREVIEW_DOMAIN = "docflow-preview-link"


def _sign_preview(
    ws_slug: str, artifact_id: uuid.UUID, revision: int, expires_at: int, secret: str
) -> str:
    message = f"{_PREVIEW_DOMAIN}:{ws_slug}:{artifact_id}:{revision}:{expires_at}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def build_preview_query(
    ws_slug: str, artifact_id: uuid.UUID, revision: int, *, ttl_seconds: int, secret: str
) -> str:
    """Query string signée (`rev=...&exp=...&sig=...`) d'un lien de preview."""
    expires_at = int(time.time()) + ttl_seconds
    sig = _sign_preview(ws_slug, artifact_id, revision, expires_at, secret)
    return f"rev={revision}&exp={expires_at}&sig={sig}"


def verify_preview_sig(
    ws_slug: str,
    artifact_id: uuid.UUID,
    revision: int,
    expires_at: int,
    sig: str,
    *,
    secret: str,
) -> bool:
    """Vérifie signature (ws + artefact + révision + expiration) en temps constant."""
    if expires_at < int(time.time()):
        return False
    expected = _sign_preview(ws_slug, artifact_id, revision, expires_at, secret)
    return hmac.compare_digest(expected, sig)

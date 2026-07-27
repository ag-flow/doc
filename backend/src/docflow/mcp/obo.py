from __future__ import annotations

import hashlib
import hmac
import time

import asyncpg
import structlog

from docflow.schemas.auth import AuthUser

log = structlog.get_logger(__name__)

# TODO(OBO item 6 — HORS périmètre de cet enabler) : ré-attribution des objets
# existants. Aujourd'hui seul workspace.owner_id est estampillé, et uniquement à
# la création. La migration/ré-attribution des workspaces déjà créés sous
# l'identité d'une clé API vers leur véritable acteur humain (via l'historique
# du portail) reste à concevoir séparément — ne PAS l'implémenter ici.

# En-têtes signés du portail (contrat OBO figé). Lecture insensible à la casse.
_HDR_ACTOR = "x-portal-actor"
_HDR_TIMESTAMP = "x-portal-actor-timestamp"
_HDR_SIGNATURE = "x-portal-actor-signature"

# Fenêtre anti-rejeu par défaut (secondes) sur le timestamp signé.
_DEFAULT_WINDOW = 300

# Contrat OBO v6 (GUID-only) : l'acteur est le GUID d'identité posé par
# l'utilisateur dans son profil (app_user.identity) — JAMAIS le sub OIDC,
# jamais login/email. Modèle uniforme OIDC/local.
_SELECT_USER_BY_IDENTITY = """
SELECT id, email, label, is_admin, validated, disabled
FROM app_user
WHERE identity = $1
"""


def verify_actor(
    actor: str,
    timestamp: str,
    signature: str,
    api_key: str,
    *,
    window: int = _DEFAULT_WINDOW,
    now: float | None = None,
) -> bool:
    """Vérifie la signature OBO du portail (recette figée, sécurité-critique).

    Secret HMAC = la clé API en clair présentée sur la MÊME requête. Charge
    canonique = octets exacts de ``f"{actor}\\n{timestamp}"``. Comparaison en
    temps constant. Fenêtre anti-rejeu de ``window`` secondes sur le timestamp.
    Un timestamp non entier ⇒ False (jamais d'exception). ``now`` injectable.
    """
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False

    reference = time.time() if now is None else now
    if abs(reference - ts) > window:
        return False

    payload = f"{actor}\n{timestamp}".encode()
    expected = hmac.new(api_key.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _header(headers: object, name: str) -> str | None:
    """Lecture d'un en-tête insensible à la casse ; None si absent."""
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    value = getter(name)
    return value if isinstance(value, str) else None


async def resolve_actor_user(
    pool: asyncpg.Pool,
    headers: object,
    api_key: str,
) -> AuthUser | None:
    """Résout le principal humain OBO à partir des en-têtes signés.

    Fail-safe absolu : tout écart (en-tête manquant, signature invalide/hors
    fenêtre, sub inconnu, utilisateur non validé ou désactivé) ⇒ None. Ne lève
    jamais — l'appelant retombe alors sur l'identité de la clé API.
    """
    try:
        actor = _header(headers, _HDR_ACTOR)
        timestamp = _header(headers, _HDR_TIMESTAMP)
        signature = _header(headers, _HDR_SIGNATURE)
        if actor is None or timestamp is None or signature is None:
            return None

        if not verify_actor(actor, timestamp, signature, api_key):
            return None

        async with pool.acquire() as conn:
            row = await conn.fetchrow(_SELECT_USER_BY_IDENTITY, actor)
        if row is None or row["disabled"] or not row["validated"]:
            return None

        return AuthUser(
            id=row["id"],
            email=row["email"],
            label=row["label"],
            is_admin=row["is_admin"],
            validated=row["validated"],
            disabled=row["disabled"],
        )
    except Exception:  # noqa: BLE001 — frontière de confiance : jamais d'erreur remontée
        log.warning("mcp_obo_resolve_failed", exc_info=True)
        return None

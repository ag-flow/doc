from __future__ import annotations

import re
import uuid

import asyncpg
import structlog

from docflow.secrets.secret import Secret

_VAULT_RE = re.compile(r"^\$\{vault://([^/:]+):(/.+)\}$")
# Référence vers un secret HMAC local (par id global) : ${hmac://<uuid>}.
_HMAC_RE = re.compile(r"^\$\{hmac://([0-9a-fA-F-]{36})\}$")
# Référence vers un secret utilisateur (Mes secrets) par id : ${secret://<uuid>}.
# Résolu côté serveur uniquement (worker) — jamais exposé à l'UI.
_SECRET_RE = re.compile(r"^\$\{secret://([0-9a-fA-F-]{36})\}$")

log = structlog.get_logger(__name__)


def _assert_safe_vault_path(path: str) -> None:
    """Rejette une traversée de chemin dans une référence ${vault://nom:/chemin}.

    La regex garantit déjà le `/` initial (chemin absolu). Ici on interdit tout
    segment `..` : un `${vault://w:/../autre}` tenterait de sortir du périmètre
    attendu du coffre (STANDARD « Gestion des secrets » §6 — garde anti-traversal).
    """
    if any(seg == ".." for seg in path.split("/")):
        raise ValueError(f"chemin vault invalide (traversée « .. » interdite) : {path}")


async def resolve(
    secret: Secret,
    *,
    harpocrate_url: str | None,
    pool: asyncpg.Pool | None = None,
    enc_key: str | None = None,
) -> str:
    """Résout un Secret.

    - Valeur inline (pas de ${vault://...}) → retournée telle quelle.
    - Référence vault → récupère la clé API du wallet dans la DB,
      appelle le SDK Harpocrate (sync dans un thread) et retourne la valeur déchiffrée.

    Lève ValueError si HARPOCRATE_URL absent, pool/enc_key manquants,
    ou wallet inconnu.
    """
    raw = secret.reveal()

    mh = _HMAC_RE.match(raw)
    if mh:
        if pool is None or enc_key is None:
            raise ValueError("pool and enc_key are required to resolve an hmac reference")
        from docflow.vault.service import resolve_hmac_value

        value = await resolve_hmac_value(pool, uuid.UUID(mh.group(1)), enc_key)
        if value is None:
            raise ValueError(f"Secret HMAC « {mh.group(1)} » introuvable dans la base.")
        return value

    ms = _SECRET_RE.match(raw)
    if ms:
        if pool is None or enc_key is None:
            raise ValueError("pool and enc_key are required to resolve a secret reference")
        from docflow.vault.service import resolve_user_secret_value

        value = await resolve_user_secret_value(
            pool, uuid.UUID(ms.group(1)), enc_key, harpocrate_url=harpocrate_url
        )
        if value is None:
            raise ValueError(f"Secret « {ms.group(1)} » introuvable dans la base.")
        return value

    m = _VAULT_RE.match(raw)
    if not m:
        return raw

    if pool is None or enc_key is None:
        raise ValueError("pool and enc_key are required to resolve a vault reference")

    wallet_name, path = m.group(1), m.group(2)
    _assert_safe_vault_path(path)
    log.debug("resolving_vault_secret", wallet=wallet_name, path=path)

    # Couche de résolution robuste (cache, invalidation 401/403, backoff, client réutilisé).
    from docflow.secrets.vault_fetch import fetch_vault_secret

    return await fetch_vault_secret(
        pool=pool,
        enc_key=enc_key,
        identifier=wallet_name,
        path=path,
        harpocrate_url=harpocrate_url,
    )

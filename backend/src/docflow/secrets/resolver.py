from __future__ import annotations

import asyncio
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

        value = await resolve_user_secret_value(pool, uuid.UUID(ms.group(1)), enc_key)
        if value is None:
            raise ValueError(f"Secret « {ms.group(1)} » introuvable dans la base.")
        return value

    m = _VAULT_RE.match(raw)
    if not m:
        return raw

    if not harpocrate_url:
        raise ValueError("Secret contains a vault reference but HARPOCRATE_URL is not configured")
    if pool is None or enc_key is None:
        raise ValueError("pool and enc_key are required to resolve a vault reference")

    wallet_name, path = m.group(1), m.group(2)
    log.debug("resolving_vault_secret", wallet=wallet_name, path=path)

    # Importé ici pour éviter d'initialiser le SDK si Harpocrate n'est pas utilisé.
    from docflow.vault.service import get_api_key

    api_key = await get_api_key(pool, wallet_name, enc_key)
    if api_key is None:
        raise ValueError(f"Wallet Harpocrate « {wallet_name} » introuvable dans la base.")

    # Le SDK Harpocrate est synchrone — on l'exécute dans un thread dédié.
    def _fetch() -> str:
        from harpocrate import VaultClient

        client = VaultClient(token=api_key, base_url=harpocrate_url)
        return str(client.secrets.get(path))

    return await asyncio.to_thread(_fetch)

"""Résolution robuste des secrets de coffre (STANDARD Harpocrate §6).

Couche unique de récupération d'une valeur Harpocrate, partagée par le résolveur
`${vault://alias:/path}` et le backend vault des `${secret://uuid}`. Elle apporte
ce que le SDK ne fait pas au niveau applicatif :

- **cache mémoire** des valeurs déchiffrées (jamais persisté), TTL borné,
  **pas de cache négatif** (seuls les succès sont mémorisés) ;
- **invalidation sur 401/403** du coffre + **une** seule nouvelle tentative ;
- **backoff exponentiel** sur erreur réseau (le SDK épuise d'abord ses retries) ;
- **réutilisation** du client SDK par (url, token) ;
- messages d'erreur nommant **l'endpoint et le chemin**, jamais le token ni la
  valeur (§7).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger(__name__)

# Réglages (constantes : la conformité n'exige pas qu'ils soient configurables).
CACHE_TTL_SECONDS = 300.0
MAX_NETWORK_ATTEMPTS = 2
BACKOFF_BASE_SECONDS = 0.5


class _VaultCache:
    """Cache process-local : valeurs déchiffrées (TTL) + clients SDK réutilisables."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], tuple[str, float]] = {}
        self._clients: dict[tuple[str, str], Any] = {}

    def get_value(self, key: tuple[str, str]) -> str | None:
        hit = self._values.get(key)
        if hit is None:
            return None
        value, expiry = hit
        if expiry < time.monotonic():
            self._values.pop(key, None)
            return None
        return value

    def put_value(self, key: tuple[str, str], value: str, ttl: float) -> None:
        self._values[key] = (value, time.monotonic() + ttl)

    def invalidate_identifier(self, identifier: str) -> None:
        self._values = {k: v for k, v in self._values.items() if k[0] != identifier}

    def get_client(self, base_url: str, token: str) -> Any:
        ck = (base_url, token)
        client = self._clients.get(ck)
        if client is None:
            from harpocrate import VaultClient

            client = VaultClient(token=token, base_url=base_url)
            self._clients[ck] = client
        return client

    def drop_client(self, base_url: str, token: str) -> None:
        self._clients.pop((base_url, token), None)

    def reset(self) -> None:
        self._values.clear()
        self._clients.clear()


_cache = _VaultCache()


def reset_cache() -> None:
    """Vide le cache (valeurs + clients) — utilisé par les tests et une rotation."""
    _cache.reset()


async def fetch_vault_secret(
    *,
    pool: asyncpg.Pool,
    enc_key: str,
    identifier: str,
    path: str,
    harpocrate_url: str | None,
    ttl: float = CACHE_TTL_SECONDS,
    max_attempts: int = MAX_NETWORK_ATTEMPTS,
    backoff_base: float = BACKOFF_BASE_SECONDS,
) -> str:
    """Résout une valeur de coffre : cache → endpoint → clé locale → SDK.

    Le token n'est jamais journalisé ni inclus dans un message d'erreur.
    """
    key = (identifier, path)
    cached = _cache.get_value(key)
    if cached is not None:
        return cached

    from docflow.vault.service import get_api_key

    resolved = await get_api_key(pool, identifier, enc_key)
    if resolved is None:
        raise ValueError(f"Endpoint vault « {identifier} » introuvable dans la base.")
    token, endpoint_url = resolved
    base_url = endpoint_url or harpocrate_url
    if not base_url:
        raise ValueError(
            f"URL du coffre non configurée pour l'endpoint « {identifier} » "
            f"(chemin « {path} »)."
        )

    value = await asyncio.to_thread(
        _fetch_sync, base_url, token, identifier, path, max_attempts, backoff_base
    )
    # Pas de cache négatif : on ne mémorise qu'un succès.
    _cache.put_value(key, value, ttl)
    return value


def _fetch_sync(
    base_url: str,
    token: str,
    identifier: str,
    path: str,
    max_attempts: int,
    backoff_base: float,
) -> str:
    """Appel SDK synchrone résilient (exécuté dans un thread)."""
    from harpocrate.exceptions import PermissionDenied, VaultHttpError

    auth_retry_done = False
    net_attempt = 0
    while True:
        client = _cache.get_client(base_url, token)
        try:
            return str(client.secrets.get(path))
        except PermissionDenied as exc:  # 403
            if not auth_retry_done:
                auth_retry_done = True
                _cache.invalidate_identifier(identifier)
                _cache.drop_client(base_url, token)
                log.warning("vault_permission_denied_retry", endpoint=identifier, path=path)
                continue
            raise ValueError(
                f"Accès refusé au coffre « {identifier} » (chemin « {path} ») "
                f"après invalidation : permission insuffisante."
            ) from exc
        except VaultHttpError as exc:
            code = exc.status_code
            if code in (401, 403) and not auth_retry_done:
                auth_retry_done = True
                _cache.invalidate_identifier(identifier)
                _cache.drop_client(base_url, token)
                log.warning(
                    "vault_auth_error_retry", endpoint=identifier, path=path, status=code
                )
                continue
            if code == 0 and net_attempt < max_attempts - 1:
                net_attempt += 1
                _cache.drop_client(base_url, token)
                log.warning(
                    "vault_network_retry", endpoint=identifier, path=path, attempt=net_attempt
                )
                time.sleep(backoff_base * (2 ** (net_attempt - 1)))
                continue
            raise ValueError(
                f"Échec de résolution du coffre « {identifier} » "
                f"(chemin « {path} », statut {code})."
            ) from exc

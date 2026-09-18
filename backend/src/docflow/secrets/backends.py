"""Fabrique de backends de secrets (STANDARD Harpocrate §5).

Un secret utilisateur est résolu selon son `storage_type` :
- `local`  → valeur chiffrée en base (Fernet), déchiffrée ici ;
- `vault`  → valeur dans Harpocrate, récupérée via l'endpoint référencé.

Chaque backend expose `async get(secret_row) -> str`. Contrairement au modèle
« adressage par chemin » du standard, les secrets locaux de docflow portent leur
valeur en ligne (pas de chemin) : le backend résout donc une LIGNE de secret, pas
un chemin nu. Aucun repli automatique entre backends (fail closed).
"""

from __future__ import annotations

import asyncio
from typing import Protocol

import asyncpg

from docflow.crypto import decrypt_str


class SecretBackend(Protocol):
    async def get(self, secret_row: asyncpg.Record) -> str: ...


class LocalBackend:
    """Secret local : valeur chiffrée en base (Fernet)."""

    def __init__(self, enc_key: str) -> None:
        self._enc_key = enc_key

    async def get(self, secret_row: asyncpg.Record) -> str:
        return decrypt_str(self._enc_key, secret_row["value_enc"])


class HarpocrateBackend:
    """Secret vault : valeur dans Harpocrate, via l'endpoint référencé.

    Chaîne : secret → endpoint (vault_identifier) → secret clé d'API local → SDK.
    """

    def __init__(
        self, pool: asyncpg.Pool, enc_key: str, harpocrate_url: str | None
    ) -> None:
        self._pool = pool
        self._enc_key = enc_key
        self._harpocrate_url = harpocrate_url

    async def get(self, secret_row: asyncpg.Record) -> str:
        from docflow.vault.service import get_api_key

        identifier = secret_row["vault_identifier"]
        path = secret_row["vault_path"]
        resolved = await get_api_key(self._pool, identifier, self._enc_key)
        if resolved is None:
            raise ValueError(f"Endpoint vault « {identifier} » introuvable dans la base.")
        token, endpoint_url = resolved
        base_url = endpoint_url or self._harpocrate_url
        if not base_url:
            raise ValueError(
                f"URL du coffre non configurée pour l'endpoint « {identifier} » "
                f"(chemin « {path} »)."
            )

        def _fetch() -> str:
            from harpocrate import VaultClient

            client = VaultClient(token=token, base_url=base_url)
            return str(client.secrets.get(path))

        return await asyncio.to_thread(_fetch)


def create_backend(
    storage_type: str,
    *,
    pool: asyncpg.Pool,
    enc_key: str,
    harpocrate_url: str | None = None,
) -> SecretBackend:
    """Sélectionne le backend d'un secret selon son stockage. Aucun repli."""
    if storage_type == "local":
        return LocalBackend(enc_key)
    if storage_type == "vault":
        return HarpocrateBackend(pool, enc_key, harpocrate_url)
    raise ValueError(f"storage_type inconnu : {storage_type!r}")

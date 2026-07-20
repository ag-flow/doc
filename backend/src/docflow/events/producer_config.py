"""Service de la config runtime du producteur d'events (table singleton).

Lit/écrit la ligne unique `events_producer_config` (id = true). L'admin la
pilote via le router ; le worker et l'outbox la relisent pour se reconfigurer à
chaud. `secret_ref` reste une référence vault (jamais de secret en clair ici).
"""

from __future__ import annotations

from typing import Any

import asyncpg

from docflow.events import catalog

_SELECT = """
SELECT enabled, ingestion_url, source_id, source_uri, secret_ref, allowed_events, updated_at
FROM events_producer_config WHERE id = true
"""


async def _ensure_row(conn: asyncpg.Connection) -> dict[str, Any]:
    """Retourne la ligne singleton, la créant avec ses défauts si absente."""
    row = await conn.fetchrow(_SELECT)
    if row is None:
        await conn.execute(
            "INSERT INTO events_producer_config (id) VALUES (true) ON CONFLICT (id) DO NOTHING"
        )
        row = await conn.fetchrow(_SELECT)
    assert row is not None
    return dict(row)


async def get_config(pool: asyncpg.Pool) -> dict[str, Any]:
    """Lit la config (crée la ligne par défaut si elle n'existe pas encore)."""
    async with pool.acquire() as conn:
        return await _ensure_row(conn)


async def update_config(pool: asyncpg.Pool, data: dict[str, Any]) -> dict[str, Any]:
    """Applique `data` (champs déjà validés) sur la ligne singleton (upsert).

    Fusionne avec l'existant puis réécrit toutes les colonnes en SQL statique
    paramétré — aucune SQL dynamique. Seuls les champs présents dans `data`
    remplacent la valeur courante.
    """
    async with pool.acquire() as conn, conn.transaction():
        current = await _ensure_row(conn)
        m = {**current, **data}
        row = await conn.fetchrow(
            """
            UPDATE events_producer_config
            SET enabled = $1, ingestion_url = $2, source_id = $3, source_uri = $4,
                secret_ref = $5, allowed_events = $6, updated_at = now()
            WHERE id = true
            RETURNING enabled, ingestion_url, source_id, source_uri,
                      secret_ref, allowed_events, updated_at
            """,
            m["enabled"],
            m["ingestion_url"],
            m["source_id"],
            m["source_uri"],
            m["secret_ref"],
            list(m["allowed_events"]),
        )
    assert row is not None
    return dict(row)


async def seed_from_env_if_empty(pool: asyncpg.Pool, settings: Any) -> None:
    """Seed initial depuis l'env si la config n'a JAMAIS été posée.

    « Jamais posée » = enabled false ET ingestion_url NULL. Ne fait rien si une
    config existe déjà (aucun écrasement) ou si l'env n'est pas configuré. Le
    secret env reste dans les settings : `secret_ref` reste NULL — l'admin doit
    poser une référence vault pour que le worker draine (cf. `worker._drainable`).
    """
    from docflow.events.worker import emission_configured

    async with pool.acquire() as conn, conn.transaction():
        current = await _ensure_row(conn)
        if current["enabled"] or current["ingestion_url"] is not None:
            return  # déjà configurée → on ne touche à rien
        if not emission_configured(settings):
            return
        # Migrer le secret UNIQUEMENT s'il s'agit d'une référence vault (un
        # pointeur, jamais le secret en clair) → l'upgrade d'une instance déjà
        # configurée en env (référence vault, cas recommandé) ne coupe pas la
        # livraison. Un secret inline reste hors base : secret_ref NULL, l'admin
        # devra poser une référence vault.
        env_secret = getattr(settings, "workflow_hmac_secret", None)
        raw = ""
        if env_secret is not None:
            raw = env_secret.reveal() if hasattr(env_secret, "reveal") else str(env_secret)
        secret_ref = raw if raw.startswith("${vault://") else None
        await conn.execute(
            """
            UPDATE events_producer_config
            SET enabled = true, ingestion_url = $1, source_id = $2,
                source_uri = $3, secret_ref = $4, allowed_events = $5, updated_at = now()
            WHERE id = true
            """,
            str(settings.workflow_ingestion_url),
            settings.workflow_source_id,
            settings.event_source,
            secret_ref,
            list(catalog.CATALOG.keys()),
        )

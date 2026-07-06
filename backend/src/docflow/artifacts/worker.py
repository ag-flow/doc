from __future__ import annotations

import asyncio

import asyncpg
import structlog

from docflow.artifacts.service import purge_stale
from docflow.config.settings import Settings

log = structlog.get_logger(__name__)

_TICK_SECONDS = 3600  # une passe de purge par heure suffit largement


async def purge_loop(pool: asyncpg.Pool, settings: Settings) -> None:
    """Purge périodique des artefacts jamais référencés (brouillons abandonnés).

    Les artefacts dont la dernière référence disparaît sont supprimés
    immédiatement dans la transaction du save/delete ; cette boucle ne couvre
    que le cas d'une image collée dans un brouillon jamais enregistré.
    """
    while True:
        await asyncio.sleep(_TICK_SECONDS)
        try:
            purged = await purge_stale(pool, older_than_hours=settings.artifact_purge_after_hours)
            if purged:
                log.info("artifact_purge", purged=purged)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.error("artifact_purge_failed", exc_info=True)

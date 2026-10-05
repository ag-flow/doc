from __future__ import annotations

import asyncio

import asyncpg
import structlog

from docflow.artifacts.service import purge_stale
from docflow.artifacts.uploads import purge_expired as purge_expired_uploads
from docflow.config.settings import Settings
from docflow.datasets.references import purge_stale_datasets

log = structlog.get_logger(__name__)

_TICK_SECONDS = 3600  # une passe de purge par heure suffit largement


async def purge_loop(pool: asyncpg.Pool, settings: Settings) -> None:
    """Purge périodique des artefacts et datasets jamais référencés.

    Les artefacts / datasets dont la dernière référence disparaît sont
    supprimés immédiatement dans la transaction du save ; cette boucle ne
    couvre que le cas d'un binaire ou d'un dataset créé dans un brouillon
    jamais enregistré (aucune référence ne sera jamais posée).
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
        try:
            purged_ds = await purge_stale_datasets(
                pool, older_than_hours=settings.dataset_purge_after_hours
            )
            if purged_ds:
                log.info("dataset_purge", purged=purged_ds)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.error("dataset_purge_failed", exc_info=True)
        try:
            # Tickets d'upload expirés (et leur blob temporaire) : usage unique
            # non consommé, ou PUT jamais suivi de create_artifact.
            purged_up = await purge_expired_uploads(pool)
            if purged_up:
                log.info("upload_ticket_purge", purged=purged_up)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.error("upload_ticket_purge_failed", exc_info=True)

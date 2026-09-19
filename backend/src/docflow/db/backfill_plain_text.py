"""Reprise des révisions antérieures à la colonne `plain_text` (épic MLD — F3b).

La migration `0075` ajoute la colonne vide : la projection texte ne peut pas
être calculée en SQL, elle exige le codec du type de contenu. Cette commande la
calcule pour les révisions écrites AVANT la migration.

    python -m docflow.db.backfill_plain_text

**Idempotente** : ne traite que `plain_text IS NULL`, donc un rejeu ne fait
rien. Sans danger sur une base déjà reprise, et reprenable après interruption.

Tant qu'elle n'a pas tourné, rien n'est cassé : la recherche retombe sur
`COALESCE(plain_text, content)`, c'est-à-dire le comportement d'avant.
"""

from __future__ import annotations

import asyncio

import asyncpg
import structlog

from docflow.codecs import codec_for
from docflow.config.settings import Settings

log = structlog.get_logger(__name__)

#: Traité par lots : une révision peut peser lourd, on ne charge pas tout.
BATCH_SIZE = 500

# Le type de contenu vit sur le document, pas sur la révision : on le joint.
_SELECT_BATCH = """
SELECT dv.version_technical_key AS id,
       dv.content               AS content,
       d.type                   AS content_type
FROM document_version dv
JOIN document d ON d.doc_technical_key = dv.document_ref
WHERE dv.plain_text IS NULL
LIMIT $1
"""

_UPDATE_SQL = """
UPDATE document_version SET plain_text = $2 WHERE version_technical_key = $1
"""


async def backfill(pool: asyncpg.Pool, batch_size: int = BATCH_SIZE) -> int:
    """Calcule `plain_text` pour toute révision qui en manque. Retourne le total.

    Chaque lot est écrit dans sa propre transaction : une interruption laisse
    les lots déjà faits acquis, et le rejeu reprend là où il s'est arrêté.
    """
    total = 0
    while True:
        async with pool.acquire() as conn:
            rows = await conn.fetch(_SELECT_BATCH, batch_size)
            if not rows:
                break
            updates = [
                (r["id"], codec_for(r["content_type"]).to_plain_text(r["content"])) for r in rows
            ]
            async with conn.transaction():
                await conn.executemany(_UPDATE_SQL, updates)
        total += len(rows)
        log.info("backfill_plain_text_batch", done=total)
        # Dernier lot incomplet = plus rien à faire.
        if len(rows) < batch_size:
            break
    return total


async def _main() -> None:
    settings = Settings()
    pool = await asyncpg.create_pool(settings.database_url)
    assert pool is not None
    try:
        total = await backfill(pool)
        log.info("backfill_plain_text_done", revisions=total)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_main())

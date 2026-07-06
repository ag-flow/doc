from __future__ import annotations

import asyncio
import pathlib

import asyncpg
import structlog

log = structlog.get_logger(__name__)

_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent.parent.parent / "migrations"

_CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT        PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

# Clé arbitraire mais stable pour le verrou consultatif Postgres (session-level).
# Évite la course entre deux instances démarrant simultanément sur la même base :
# sans lui, la lecture de schema_migrations et l'application se font dans des
# transactions séparées et deux instances peuvent tenter d'appliquer la même
# migration en même temps (la seconde crashe au boot sur la PK `version`).
_ADVISORY_LOCK_KEY = 0x646F_6366_6C6F_77  # "docflow" (ascii, tronqué à 64 bits)


async def apply(pool: asyncpg.Pool) -> None:
    """Apply all pending SQL migrations idempotently.

    Each migration file runs in its own transaction. Already-applied
    migrations (tracked in schema_migrations) are skipped. Safe to call
    repeatedly — subsequent calls are no-ops when no new files are present.

    Tenu par un `pg_advisory_lock` pour toute la durée de l'opération (une
    seule connexion, car le verrou est lié à la session) : deux instances
    démarrant en même temps se sérialisent au lieu de se marcher dessus.
    """
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", _ADVISORY_LOCK_KEY)
        try:
            await conn.execute(_CREATE_MIGRATIONS_TABLE)
            applied: set[str] = {
                row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")
            }

            pending = sorted(p for p in _MIGRATIONS_DIR.glob("*.sql") if p.stem not in applied)

            if not pending:
                log.info("migrations_up_to_date", count=len(applied))
                return

            for path in pending:
                version = path.stem
                log.info("applying_migration", version=version)
                async with conn.transaction():
                    await conn.execute(path.read_text())
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1)",
                        version,
                    )
                log.info("migration_applied", version=version)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _ADVISORY_LOCK_KEY)


async def _main() -> None:
    from docflow.config.settings import Settings
    from docflow.db.pool import close_pool, open_pool

    settings = Settings()
    pool = await open_pool(settings.database_url)
    try:
        await apply(pool)
    finally:
        await close_pool(pool)


if __name__ == "__main__":
    asyncio.run(_main())

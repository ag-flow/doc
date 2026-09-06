from __future__ import annotations

import asyncio
import logging
import pathlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import asyncpg
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from docflow.admin.users.router import router as users_router
from docflow.apikeys.router import router as apikeys_router
from docflow.artifacts.preview_router import router as preview_router
from docflow.artifacts.router import router as artifacts_router
from docflow.artifacts.types_router import admin_router as artifact_types_admin_router
from docflow.artifacts.types_router import read_router as artifact_types_read_router
from docflow.artifacts.worker import purge_loop as artifact_purge_loop
from docflow.auth.invite import router as invite_router
from docflow.auth.router import router as auth_router
from docflow.automations.router import router as automations_router
from docflow.automations.worker import worker_loop
from docflow.backup.router import router as backup_router
from docflow.backup.worker import worker_loop as backup_worker_loop
from docflow.blocks.router import router as blocks_router
from docflow.config.base_url import set_derived_base_url
from docflow.config.settings import Settings
from docflow.contracts.router import router as contracts_router
from docflow.datasets.router import router as datasets_router
from docflow.db.apply import apply
from docflow.db.pool import close_pool, open_pool
from docflow.documents.router import router as documents_router
from docflow.errors import DependentsConflictError
from docflow.events import outbox as events_outbox
from docflow.events.producer_config import seed_from_env_if_empty as seed_events_producer
from docflow.events.producer_router import router as events_producer_router
from docflow.events.router import router as events_router
from docflow.events.worker import worker_loop as events_worker_loop
from docflow.export.router import router as export_router
from docflow.mcp.router import router as mcp_router
from docflow.mcp.server import configure as configure_mcp
from docflow.me.preferences import router as me_prefs_router
from docflow.me.router import router as me_router
from docflow.oidc.router import router as oidc_router
from docflow.properties.router import router as properties_router
from docflow.public.router import router as public_router
from docflow.reactions.router import router as reactions_router
from docflow.references.router import router as references_router
from docflow.remote.router import router as remote_router
from docflow.setup.router import router as setup_router
from docflow.templates.router import router as templates_router
from docflow.types.router import router as types_router
from docflow.vault.router import router as vault_router
from docflow.views.router import router as views_router
from docflow.webhooks.router import router as webhooks_router
from docflow.workspaces.router import router as workspaces_router

log = structlog.get_logger(__name__)

_STATIC = pathlib.Path(__file__).parent.parent.parent / "static"


def _configure_logging(level: str) -> None:
    if structlog.is_configured():
        return
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", level=getattr(logging, level))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    _configure_logging(settings.log_level)
    pool = await open_pool(settings.database_url)
    await apply(pool)
    configure_mcp(pool, settings)
    # Producteur d'events : seed initial depuis l'env (si jamais configuré) puis
    # reconcile → l'émission (enqueue) est pilotée par la config DB, à chaud.
    await seed_events_producer(pool, settings)
    await events_outbox.reconcile(pool)
    app.state.pool = pool
    app.state.settings = settings
    worker_task = asyncio.create_task(worker_loop(pool, settings))
    backup_task = asyncio.create_task(backup_worker_loop(pool, settings))
    artifact_task = asyncio.create_task(artifact_purge_loop(pool, settings))
    events_task = asyncio.create_task(events_worker_loop(pool, settings))
    log.info("docflow_started")
    try:
        yield
    finally:
        worker_task.cancel()
        backup_task.cancel()
        artifact_task.cancel()
        events_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task
        with suppress(asyncio.CancelledError):
            await backup_task
        with suppress(asyncio.CancelledError):
            await artifact_task
        with suppress(asyncio.CancelledError):
            await events_task
        await close_pool(pool)
        log.info("docflow_stopped")


app = FastAPI(title="docflow", lifespan=lifespan)


@app.middleware("http")
async def _capture_base_url(request: Request, call_next: Any) -> Any:
    """Dérive l'URL de base publique depuis la requête portail si non configurée.

    Respecte X-Forwarded-Proto/Host (derrière un proxy / Cloudflare). Sert de
    repli au worker d'automation pour construire des liens absolus ({doc_url}).
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is not None and not getattr(settings, "public_base_url", None):
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if host:
            proto = request.headers.get("x-forwarded-proto") or request.url.scheme
            set_derived_base_url(f"{proto.split(',')[0].strip()}://{host.split(',')[0].strip()}")
    return await call_next(request)


@app.exception_handler(DependentsConflictError)
async def dependents_conflict_handler(_: Request, exc: DependentsConflictError) -> JSONResponse:
    """DOC-07 : suppression destructrice sans confirm → 409 informatif."""
    return JSONResponse(
        {"detail": exc.detail, "dependents": exc.dependents, "need_confirm": True},
        status_code=409,
    )


_API = "/api"
app.include_router(setup_router, prefix=_API)
app.include_router(auth_router, prefix=_API)
app.include_router(templates_router, prefix=_API)
app.include_router(users_router, prefix=_API)
app.include_router(me_router, prefix=_API)
app.include_router(me_prefs_router, prefix=_API)
app.include_router(invite_router, prefix=_API)
app.include_router(workspaces_router, prefix=_API)
app.include_router(types_router, prefix=_API)
app.include_router(properties_router, prefix=_API)
app.include_router(documents_router, prefix=_API)
app.include_router(artifacts_router, prefix=_API)
# Maquettes : origine de preview DÉDIÉE, servie à la racine (jamais sous /api).
# Le tunnel route preview.<domaine> → cet endpoint ; la route se garde elle-même
# par l'hôte (fail closed si preview_base_url non configuré).
app.include_router(preview_router)
app.include_router(artifact_types_read_router, prefix=_API)
app.include_router(artifact_types_admin_router, prefix=_API)
app.include_router(blocks_router, prefix=_API)
app.include_router(oidc_router, prefix=_API)
app.include_router(vault_router, prefix=_API)
app.include_router(mcp_router, prefix=_API)
app.include_router(webhooks_router, prefix=_API)
app.include_router(remote_router, prefix=_API)
app.include_router(backup_router, prefix=_API)
app.include_router(reactions_router, prefix=_API)
app.include_router(references_router, prefix=_API)
app.include_router(contracts_router, prefix=_API)
app.include_router(automations_router, prefix=_API)
app.include_router(events_router, prefix=_API)
app.include_router(events_producer_router, prefix=_API)
app.include_router(export_router, prefix=_API)
app.include_router(views_router, prefix=_API)
app.include_router(datasets_router, prefix=_API)
app.include_router(apikeys_router, prefix=_API)
app.include_router(public_router, prefix="/pub")


async def _check_db(pool: asyncpg.Pool) -> int:
    return await pool.fetchval("SELECT 1")  # type: ignore[no-any-return]


@app.get("/health")
async def health() -> JSONResponse:
    try:
        result = await _check_db(app.state.pool)
        return JSONResponse({"status": "ok", "db": result == 1})
    except Exception:
        log.error("health_check_failed", exc_info=True)
        return JSONResponse({"status": "error", "detail": "service unavailable"}, status_code=503)


# Fichiers statiques du frontend (assets JS/CSS)
if _STATIC.exists():
    app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")

    # SPA catch-all : sert un fichier racine existant du build (favicon.svg,
    # icons.svg, robots.txt…) s'il existe, sinon renvoie index.html. La garde
    # is_relative_to empêche toute remontée hors du répertoire statique.
    _static_root = _STATIC.resolve()

    # La coquille SPA ne doit JAMAIS être mise en cache : sinon le navigateur
    # garde un index.html périmé qui référence un ancien bundle hashé, et
    # l'utilisateur reste sur du code obsolète après un déploiement. Les assets
    # /assets/* sont hashés par contenu → sûrs à cacher (nom neuf à chaque build).
    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        if full_path:
            candidate = (_STATIC / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(_static_root):
                # favicon.svg / icons.svg ne sont pas hashés : revalidation aussi.
                return FileResponse(candidate, headers=_NO_CACHE)
        return FileResponse(_STATIC / "index.html", headers=_NO_CACHE)

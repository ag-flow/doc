from __future__ import annotations

import asyncio
import logging
import pathlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import asyncpg
import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from docflow.admin.users.router import router as users_router
from docflow.auth.router import router as auth_router
from docflow.automations.router import router as automations_router
from docflow.automations.worker import worker_loop
from docflow.blocks.router import router as blocks_router
from docflow.config.settings import Settings
from docflow.contracts.router import router as contracts_router
from docflow.db.apply import apply
from docflow.db.pool import close_pool, open_pool
from docflow.documents.router import router as documents_router
from docflow.mcp.router import router as mcp_router
from docflow.mcp.server import configure as configure_mcp
from docflow.oidc.router import router as oidc_router
from docflow.properties.router import router as properties_router
from docflow.public.router import router as public_router
from docflow.reactions.router import router as reactions_router
from docflow.references.router import router as references_router
from docflow.setup.router import router as setup_router
from docflow.templates.router import router as templates_router
from docflow.types.router import router as types_router
from docflow.vault.router import router as vault_router
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
    configure_mcp(pool)
    app.state.pool = pool
    app.state.settings = settings
    worker_task = asyncio.create_task(worker_loop(pool, settings))
    log.info("docflow_started")
    try:
        yield
    finally:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task
        await close_pool(pool)
        log.info("docflow_stopped")


app = FastAPI(title="docflow", lifespan=lifespan)
_API = "/api"
app.include_router(setup_router, prefix=_API)
app.include_router(auth_router, prefix=_API)
app.include_router(templates_router, prefix=_API)
app.include_router(users_router, prefix=_API)
app.include_router(workspaces_router, prefix=_API)
app.include_router(types_router, prefix=_API)
app.include_router(properties_router, prefix=_API)
app.include_router(documents_router, prefix=_API)
app.include_router(blocks_router, prefix=_API)
app.include_router(oidc_router, prefix=_API)
app.include_router(vault_router, prefix=_API)
app.include_router(mcp_router, prefix=_API)
app.include_router(webhooks_router, prefix=_API)
app.include_router(reactions_router, prefix=_API)
app.include_router(references_router, prefix=_API)
app.include_router(contracts_router, prefix=_API)
app.include_router(automations_router, prefix=_API)
app.include_router(public_router, prefix="/pub")


async def _check_db(pool: asyncpg.Pool) -> int:
    return await pool.fetchval("SELECT 1")  # type: ignore[no-any-return]


@app.get("/health")
async def health() -> JSONResponse:
    try:
        result = await _check_db(app.state.pool)
        return JSONResponse({"status": "ok", "db": result == 1})
    except Exception as exc:
        log.error("health_check_failed", error=str(exc))
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)


# Fichiers statiques du frontend (assets JS/CSS)
if _STATIC.exists():
    app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")

    # SPA catch-all : toute route non-API renvoie index.html
    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        return FileResponse(_STATIC / "index.html")

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request, Response
from mcp.server.sse import SseServerTransport

from docflow.auth.deps import require_admin
from docflow.mcp.server import mcp_server

log = structlog.get_logger(__name__)

router = APIRouter(tags=["mcp"])

_transport = SseServerTransport("/api/mcp/messages")


@router.get("/mcp/sse")
async def mcp_sse(
    request: Request,
    _: object = Depends(require_admin),
) -> Response:
    """Point d'entrée SSE du serveur MCP (nécessite JWT admin)."""
    async with _transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )
    return Response()


@router.post("/mcp/messages")
async def mcp_messages(request: Request) -> Response:
    """Endpoint de réception des messages MCP (session_id en query param)."""
    await _transport.handle_post_message(
        request.scope, request.receive, request._send
    )
    return Response()

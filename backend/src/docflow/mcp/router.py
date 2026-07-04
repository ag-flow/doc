from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request, Response
from mcp.server.sse import SseServerTransport

from docflow.auth.deps import require_admin
from docflow.mcp.server import mcp_server, reset_current_identity, set_current_identity
from docflow.schemas.auth import AuthUser

log = structlog.get_logger(__name__)

router = APIRouter(tags=["mcp"])

_transport = SseServerTransport("/api/mcp/messages")


@router.get("/mcp/sse")
async def mcp_sse(
    request: Request,
    user: AuthUser = Depends(require_admin),
) -> Response:
    """Point d'entrée SSE du serveur MCP (nécessite JWT admin).

    L'identité authentifiée est liée au contexte de la session : la boucle de
    dispatch des messages (et donc les outils d'écriture) hérite de cette
    ContextVar et attribue les ressources créées à l'appelant réel.
    """
    token = set_current_identity(user)
    try:
        async with _transport.connect_sse(request.scope, request.receive, request._send) as (
            read_stream,
            write_stream,
        ):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )
    finally:
        reset_current_identity(token)
    return Response()


@router.post("/mcp/messages")
async def mcp_messages(
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> Response:
    """Réception des messages MCP (session_id en query param).

    Défense en profondeur (INT-04) : cet endpoint reçoit toutes les invocations
    d'outils, y compris les écritures. Il applique la même dépendance d'auth que
    le canal SSE au lieu de se reposer uniquement sur le secret du session_id.
    """
    await _transport.handle_post_message(request.scope, request.receive, request._send)
    return Response()

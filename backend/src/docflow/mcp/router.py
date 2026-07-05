from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request, Response
from mcp.server.sse import SseServerTransport

from docflow.auth.deps import require_authenticated
from docflow.mcp.server import mcp_server
from docflow.mcp.session import McpSession, reset_current_session, set_current_session
from docflow.schemas.auth import AuthUser

log = structlog.get_logger(__name__)

router = APIRouter(tags=["mcp"])

_transport = SseServerTransport("/api/mcp/messages")


def _build_session(request: Request, user: AuthUser) -> McpSession:
    """Session MCP dérivée de l'authentification HTTP (JWT ou clé API).

    Pour une clé API, get_current_user a déposé les scopes et le flag admin du
    profil dans request.state : la session les porte pour que le dispatch des
    outils applique le périmètre du profil. Pour un JWT, scopes = None (accès
    complet, comme sur l'API REST).
    """
    return McpSession(
        user=user,
        api_key_scopes=getattr(request.state, "api_key_scopes", None),
        api_key_admin=bool(getattr(request.state, "api_key_is_admin", False)),
    )


@router.get("/mcp/sse")
async def mcp_sse(
    request: Request,
    user: AuthUser = Depends(require_authenticated),
) -> Response:
    """Point d'entrée SSE du serveur MCP (JWT de session OU clé API en Bearer).

    L'identité authentifiée est liée au contexte de la session : la boucle de
    dispatch des messages (et donc les outils d'écriture) hérite de cette
    ContextVar et attribue les ressources créées à l'appelant réel. Pour une
    clé API, le périmètre du profil (scopes / admin) est appliqué aux outils.
    """
    token = set_current_session(_build_session(request, user))
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
        reset_current_session(token)
    return Response()


@router.post("/mcp/messages")
async def mcp_messages(
    request: Request,
    _: AuthUser = Depends(require_authenticated),
) -> Response:
    """Réception des messages MCP (session_id en query param).

    Défense en profondeur (INT-04) : cet endpoint reçoit toutes les invocations
    d'outils, y compris les écritures. Il applique la même dépendance d'auth que
    le canal SSE au lieu de se reposer uniquement sur le secret du session_id.
    """
    await _transport.handle_post_message(request.scope, request.receive, request._send)
    return Response()

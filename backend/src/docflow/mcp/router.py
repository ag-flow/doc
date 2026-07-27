from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.security import HTTPBearer
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from docflow.auth.deps import get_current_user
from docflow.mcp.obo import resolve_actor_user
from docflow.mcp.server import _get_pool, mcp_server
from docflow.mcp.session import McpSession, reset_current_session, set_current_session
from docflow.schemas.auth import AuthUser

log = structlog.get_logger(__name__)

router = APIRouter(tags=["mcp"])

_transport = SseServerTransport("/api/mcp/messages")

_bearer = HTTPBearer(auto_error=False)

# Sérialisation des POST /mcp/messages par session : le SDK répond 202 AVANT
# d'enfiler le message dans le flux de la session ; deux POST successifs
# (notifications/initialized puis tools/list) peuvent donc s'enfiler dans le
# désordre et faire rejeter une requête valide (« received request before
# initialization was complete »). Un verrou par session garantit que l'ordre
# de traitement suit l'ordre d'arrivée. Créé au premier POST d'une session,
# retiré dès qu'un POST constate que la session n'existe plus côté transport.
_session_locks: dict[UUID, asyncio.Lock] = {}


class _AsgiEndpoint:
    """Adaptateur : force Starlette à traiter le handler comme une app ASGI.

    Une fonction passée à Route() serait interprétée comme `func(request) →
    Response` ; or ces handlers répondent eux-mêmes sur le cycle HTTP (SSE,
    202 du transport). Une réponse supplémentaire provoquerait un second
    ``http.response.start`` — uvicorn fermait alors la connexion keep-alive
    et le message suivant d'un client MCP était perdu.
    """

    def __init__(self, handler: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self._handler = handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._handler(scope, receive, send)


async def _authenticate(request: Request) -> tuple[AuthUser, str | None] | None:
    """Même dépendance d'auth que l'API REST (JWT ou clé API), en contexte ASGI.

    Retourne ``(user, raw_api_key)`` où ``raw_api_key`` est la clé API en clair
    présentée (None pour une session JWT), ou None si une réponse d'erreur a déjà
    été renvoyée. La clé brute sert de secret HMAC pour l'OBO first-party.
    """
    try:
        credentials = await _bearer(request)
        user = await get_current_user(request, credentials)
    except HTTPException as exc:
        response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        await response(request.scope, request.receive, request._send)  # noqa: SLF001
        return None
    # Une session clé API est identifiée par la présence de scopes dans state
    # (get_current_user les y dépose). Un JWT n'a pas de clé API en clair et
    # identifie déjà l'humain : l'OBO ne s'y applique pas.
    raw_api_key: str | None = None
    if credentials is not None and getattr(request.state, "api_key_scopes", None) is not None:
        raw_api_key = credentials.credentials
    return user, raw_api_key


async def _build_session(request: Request, user: AuthUser, raw_api_key: str | None) -> McpSession:
    """Session MCP dérivée de l'authentification HTTP (JWT ou clé API).

    Pour une clé API, get_current_user a déposé les scopes et le flag admin du
    profil dans request.state : la session les porte pour que le dispatch des
    outils applique le périmètre du profil. Pour un JWT, scopes = None (accès
    complet, comme sur l'API REST).

    Frontière de confiance OBO : pour une session clé API, on tente de résoudre
    le principal humain à partir des en-têtes signés du portail (secret =
    ``raw_api_key``). Toute anomalie ⇒ ``actor_user=None`` (fail-safe) : jamais
    de 401, on retombe sur l'identité de la clé. Jamais pour un JWT.
    """
    actor_user: AuthUser | None = None
    if raw_api_key is not None:
        actor_user = await resolve_actor_user(_get_pool(), request.headers, raw_api_key)
    return McpSession(
        user=user,
        api_key_scopes=getattr(request.state, "api_key_scopes", None),
        api_key_admin=bool(getattr(request.state, "api_key_is_admin", False)),
        actor_user=actor_user,
    )


async def _mcp_sse(scope: Scope, receive: Receive, send: Send) -> None:
    """Point d'entrée SSE du serveur MCP (JWT de session OU clé API en Bearer).

    L'identité authentifiée est liée au contexte de la session : la boucle de
    dispatch des messages (et donc les outils d'écriture) hérite de cette
    ContextVar et attribue les ressources créées à l'appelant réel. Pour une
    clé API, le périmètre du profil (scopes / admin) est appliqué aux outils.
    """
    request = Request(scope, receive, send)
    authed = await _authenticate(request)
    if authed is None:
        return
    user, raw_api_key = authed
    token = set_current_session(await _build_session(request, user, raw_api_key))
    try:
        async with _transport.connect_sse(scope, receive, send) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )
    finally:
        reset_current_session(token)
        # Balayage des verrous orphelins (sessions fermées sans POST ultérieur).
        live = _transport._read_stream_writers.keys()  # noqa: SLF001
        for sid in [sid for sid in _session_locks if sid not in live]:
            _session_locks.pop(sid, None)


async def _mcp_messages(scope: Scope, receive: Receive, send: Send) -> None:
    """Réception des messages MCP (session_id en query param).

    Défense en profondeur (INT-04) : cet endpoint reçoit toutes les invocations
    d'outils, y compris les écritures. Il applique la même dépendance d'auth que
    le canal SSE au lieu de se reposer uniquement sur le secret du session_id.
    """
    request = Request(scope, receive, send)
    if await _authenticate(request) is None:
        return

    session_id: UUID | None = None
    raw_session_id = request.query_params.get("session_id")
    if raw_session_id:
        try:
            session_id = UUID(hex=raw_session_id)
        except ValueError:
            session_id = None  # malformé : le transport répondra 400 lui-même

    if session_id is None:
        await _transport.handle_post_message(scope, receive, send)
        return

    lock = _session_locks.setdefault(session_id, asyncio.Lock())
    async with lock:
        await _transport.handle_post_message(scope, receive, send)
    if session_id not in _transport._read_stream_writers:  # noqa: SLF001
        # Session inconnue ou fermée (le transport a répondu 404) : ne pas
        # laisser s'accumuler un verrou par session_id.
        _session_locks.pop(session_id, None)


# Endpoints ASGI purs (une seule réponse par cycle HTTP) : ils n'apparaissent
# pas dans l'OpenAPI, ce qui est voulu — ce n'est pas une surface REST.
router.routes.append(Route("/mcp/sse", endpoint=_AsgiEndpoint(_mcp_sse), methods=["GET"]))
router.routes.append(
    Route("/mcp/messages", endpoint=_AsgiEndpoint(_mcp_messages), methods=["POST"])
)

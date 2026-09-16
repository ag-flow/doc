"""Ingress de corrélation — middleware ASGI pur (STANDARD, A3).

Pourquoi ASGI pur et non `@app.middleware("http")` : un `BaseHTTPMiddleware`
exécute l'aval dans une tâche distincte, si bien qu'un `contextvar` posé avant
`call_next` n'est pas garanti visible par l'endpoint. Ici on appelle `self.app`
directement, dans le même contexte async : le contexte de corrélation posé est
vu par le service qui `enqueue` un event pendant la requête.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docflow.observability import correlation as corr

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class CorrelationMiddleware:
    """Établit le contexte de corrélation ambiant à partir des en-têtes entrants.

    FAIL-CLOSED : le contexte entrant n'est relayé QUE si la requête porte
    l'en-tête de confiance interne configuré (`settings.trace_ingress_header`),
    posé par la gateway sur le réseau interne. Sans lui — appelant externe, UI —
    aucun contexte n'est établi : le fil naîtra `kind=document` à l'`enqueue`.
    Un `traceparent` d'appelant non vouché n'est jamais accepté comme parent
    (STANDARD §4) ; sa prise en compte en attribut `peer.trace_ref` relève du
    lot d'export (B), quand un span d'ingress existera pour le porter.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        ctx = self._inbound_context(scope)
        token = corr.bind(ctx) if ctx is not None else None
        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                corr.reset(token)

    @staticmethod
    def _inbound_context(scope: Scope) -> corr.CorrelationContext | None:
        state = getattr(scope.get("app"), "state", None)
        header_name = getattr(getattr(state, "settings", None), "trace_ingress_header", None)
        if not header_name:
            return None
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if not headers.get(header_name.lower()):
            return None  # marqueur interne absent → on ne fait jamais confiance
        return corr.from_headers(headers)

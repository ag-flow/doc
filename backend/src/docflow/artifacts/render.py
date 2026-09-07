"""Port de rendu HTML → PNG des maquettes (capacité OPTIONNELLE).

Contrat minimal : HTML autoportant + largeur de cadre en entrée, PNG en sortie.
Résolu par configuration (`render_service_url`). NON configuré = pas de rendu
(dégradé assumé, jamais une installation cassée).

EXIGENCE DE SÉCURITÉ (à la charge de l'opérateur) : le service de rendu exécute
du HTML NON FIABLE côté serveur. Il DOIT être isolé — aucun réseau sortant,
conteneur éphémère — sinon c'est un SSRF / une exfiltration des maquettes. Le
compose dev place le moteur sur un réseau `internal: true` (sans route Internet).

L'implémentation cible un service compatible Browserless (`POST /screenshot`,
corps `{html, viewport, options}`, réponse `image/png`) ; le reste du code ne
connaît que le port `render_png`.
"""

from __future__ import annotations

import httpx
import structlog

from docflow.config.settings import Settings

log = structlog.get_logger(__name__)

# Largeurs simulées par viewport (px) — miroir du frontend (MaquetteBlock).
VIEWPORT_WIDTH: dict[str, int] = {
    "mobile": 390,
    "tablette": 768,
    "tablet": 768,
    "desktop": 1024,
}
_DEFAULT_WIDTH = 1024
_DEFAULT_HEIGHT = 900
_MAX_WIDTH = 4096


class RenderNotConfigured(Exception):
    """Aucun service de rendu configuré (`render_service_url` absent)."""


class RenderError(Exception):
    """Le service de rendu a échoué (injoignable, erreur HTTP, réponse vide)."""


def resolve_width(viewport: str | None, width: int | None) -> int:
    """Largeur du cadre en px : `width` explicite > preset viewport > desktop."""
    if width is not None and width > 0:
        return min(width, _MAX_WIDTH)
    if viewport:
        preset = VIEWPORT_WIDTH.get(viewport.strip().lower())
        if preset is not None:
            return preset
    return _DEFAULT_WIDTH


async def render_png(
    settings: Settings, html: str, *, width: int, height: int = _DEFAULT_HEIGHT
) -> bytes:
    """Rend le HTML en PNG via le service configuré.

    Lève `RenderNotConfigured` si aucun service n'est configuré, `RenderError`
    en cas d'échec du service (injoignable, code non-200, réponse vide).
    """
    base = settings.render_service_url
    if not base:
        raise RenderNotConfigured()
    params: dict[str, str] = {}
    if settings.render_service_token is not None:
        params["token"] = settings.render_service_token.reveal()
    payload = {
        "html": html,
        "viewport": {"width": width, "height": height, "deviceScaleFactor": 2},
        "options": {"type": "png", "fullPage": True},
    }
    url = f"{base.rstrip('/')}/screenshot"
    try:
        async with httpx.AsyncClient(timeout=settings.render_timeout_seconds) as client:
            resp = await client.post(url, params=params, json=payload)
    except httpx.HTTPError as exc:
        log.warning("render_service_unreachable", error=str(exc))
        raise RenderError(f"service de rendu injoignable : {exc}") from exc
    if resp.status_code != 200:
        log.warning("render_service_http_error", status=resp.status_code)
        raise RenderError(f"service de rendu : HTTP {resp.status_code}")
    if not resp.content:
        raise RenderError("service de rendu : réponse vide")
    return resp.content

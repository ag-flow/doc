"""Serveur de preview des maquettes HTML (fiche 6dd1e16d).

Une maquette est du HTML **non fiable** (généré par un agent, JS autorisé). Il
n'est JAMAIS servi depuis l'origine authentifiée de docflow : ce routeur le rend
UNIQUEMENT sur l'origine de preview DÉDIÉE (`preview_base_url`), en iframe
sandboxée côté consommateur, avec une CSP fermée côté serveur. La réponse est
l'isolation, pas le filtrage (cf. ADR « Canal .html des maquettes »).
"""

from __future__ import annotations

import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from docflow.artifacts import mutable, render
from docflow.artifacts.links import verify_preview_sig

router = APIRouter(tags=["preview"])

# CSP fermée : aucune ressource externe (la maquette est autoportante), pas de
# canal d'exfiltration (`connect-src` absent → 'none'), styles/scripts inline
# seulement (une maquette embarque tout), images/fonts en data: URI.
_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
    "img-src data:; font-src data:;"
)

# Mesure de hauteur injectée par LE SERVEUR (jamais écrite par l'agent, jamais
# persistée) : le sandbox sans allow-same-origin empêche le parent de lire le
# DOM de l'iframe, la hauteur remonte donc par postMessage. Le parent filtre sur
# l'origine de preview.
_MEASURE_SCRIPT = (
    "<script>(function(){function h(){try{parent.postMessage("
    "{type:'docflow-preview-height',height:document.documentElement.scrollHeight},'*')"
    "}catch(e){}}if(window.ResizeObserver){new ResizeObserver(h)"
    ".observe(document.documentElement)}window.addEventListener('load',h);h()})();</script>"
)


def _inject_measure(html: str) -> str:
    """Insère le script de mesure juste avant </body> (ou en fin si absent)."""
    idx = html.rfind("</body>")
    if idx == -1:
        return html + _MEASURE_SCRIPT
    return html[:idx] + _MEASURE_SCRIPT + html[idx:]


def _preview_host(settings: object) -> str | None:
    base = getattr(settings, "preview_base_url", None)
    return urlparse(base).hostname if base else None


@router.get("/preview/{ws_slug}/{artifact_id}.png")
async def serve_preview_png(
    ws_slug: str,
    artifact_id: uuid.UUID,
    request: Request,
    rev: int = Query(..., ge=1),
    exp: int = Query(...),
    sig: str = Query(..., min_length=64, max_length=64),
    viewport: str | None = Query(None),
    width: int | None = Query(None, ge=200, le=4096),
) -> Response:
    """Rend une révision de maquette en PNG (même lien signé que l'aperçu HTML,
    suffixe `.png`). 404 uniforme sur tout refus ; nécessite un service de rendu
    configuré. Déclarée AVANT la route HTML pour capter le suffixe `.png`."""
    settings = request.app.state.settings
    host = _preview_host(settings)
    if host is None:
        raise HTTPException(status_code=404, detail="preview non configuré")
    if request.url.hostname != host:
        raise HTTPException(status_code=404, detail="origine non autorisée")
    secret: str = settings.jwt_secret.reveal()
    if not verify_preview_sig(ws_slug, artifact_id, rev, exp, sig, secret=secret):
        raise HTTPException(status_code=404, detail="lien invalide ou expiré")
    try:
        data, media_type, _ = await mutable.fetch_revision_content(
            request.app.state.pool, ws_slug, artifact_id, rev
        )
    except HTTPException as exc:
        raise HTTPException(status_code=404, detail="maquette introuvable") from exc
    if media_type.lower() != "text/html":
        raise HTTPException(status_code=404, detail="maquette introuvable")
    frame_width = render.resolve_width(viewport, width)
    try:
        png = await render.render_png(
            settings, data.decode("utf-8", errors="replace"), width=frame_width
        )
    except render.RenderNotConfigured:
        raise HTTPException(status_code=404, detail="rendu PNG non configuré") from None
    except render.RenderError as exc:
        raise HTTPException(status_code=502, detail="échec du rendu PNG") from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


@router.get("/preview/{ws_slug}/{artifact_id}")
async def serve_preview(
    ws_slug: str,
    artifact_id: uuid.UUID,
    request: Request,
    rev: int = Query(..., ge=1),
    exp: int = Query(...),
    sig: str = Query(..., min_length=64, max_length=64),
) -> Response:
    """Rend une révision de maquette HTML. Aucune auth : le lien signé porte
    l'autorisation (émise sous RBAC par get_preview_link). 404 uniforme sur tout
    refus — aucun oracle d'existence."""
    settings = request.app.state.settings
    host = _preview_host(settings)
    # Fail closed : sans origine de preview configurée, aucun HTML n'est servi.
    if host is None:
        raise HTTPException(status_code=404, detail="preview non configuré")
    # Isolation d'origine : ce HTML ne se sert QUE sur l'hôte de preview dédié —
    # jamais sur l'origine docflow, même si la route y était routée par erreur.
    if request.url.hostname != host:
        raise HTTPException(status_code=404, detail="origine non autorisée")
    secret: str = settings.jwt_secret.reveal()
    if not verify_preview_sig(ws_slug, artifact_id, rev, exp, sig, secret=secret):
        raise HTTPException(status_code=404, detail="lien invalide ou expiré")

    try:
        data, media_type, _ = await mutable.fetch_revision_content(
            request.app.state.pool, ws_slug, artifact_id, rev
        )
    except HTTPException as exc:
        raise HTTPException(status_code=404, detail="maquette introuvable") from exc
    # Ce routeur ne sert QUE des maquettes HTML (le reste passe par /artifacts).
    if media_type.lower() != "text/html":
        raise HTTPException(status_code=404, detail="maquette introuvable")

    html = _inject_measure(data.decode("utf-8", errors="replace"))
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Content-Security-Policy": _CSP,
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
            # Lien lié à une révision (immuable), mais on évite tout cache
            # partagé d'un contenu servi sous lien signé.
            "Cache-Control": "no-store",
        },
    )

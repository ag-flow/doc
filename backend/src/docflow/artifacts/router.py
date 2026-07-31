from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from docflow.artifacts import service
from docflow.artifacts.links import build_download_query, verify_download_sig
from docflow.auth.deps import check_api_key_scope, require_authenticated
from docflow.schemas.artifact import ArtifactCreatedOut, ArtifactMetaOut
from docflow.schemas.auth import AuthUser
from docflow.workspaces.access import require_ws_access

router = APIRouter(tags=["artifacts"])

_WS = "/workspaces/{ws_slug}"
_ART = _WS + "/artifacts/{artifact_id}"
_Auth = Depends(require_authenticated)


def binary_response(data: bytes, media_type: str, filename: str, *, attachment: bool) -> Response:
    disposition = "attachment" if attachment else "inline"
    # filename* RFC 5987 inutile ici : le nom est déjà restreint au basename ;
    # on neutralise guillemets et retours pour éviter toute injection d'en-tête.
    safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "")
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'{disposition}; filename="{safe_name}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.post(_WS + "/artifacts", response_model=ArtifactCreatedOut, status_code=201,
             dependencies=[Depends(require_ws_access)])
async def upload_artifact(
    ws_slug: str,
    file: UploadFile,
    request: Request,
    user: AuthUser = _Auth,
    filename: str | None = Form(default=None),
    media_type: str | None = Form(default=None),
) -> ArtifactCreatedOut:
    """Upload multipart. `filename` et `media_type` (optionnels) surchargent
    les valeurs du fichier — le media_type reste borné à la whitelist."""
    check_api_key_scope(request, ws_slug, write=True)
    data = await file.read()
    return await service.create_artifact(
        request.app.state.pool,
        ws_slug,
        filename=filename or file.filename or "",
        data=data,
        created_by=user.id,
        max_bytes=request.app.state.settings.artifact_max_bytes,
        media_type_override=media_type,
    )


@router.get(_ART + "/meta", response_model=ArtifactMetaOut,
            dependencies=[Depends(require_ws_access)])
async def get_artifact_meta(
    ws_slug: str, artifact_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> ArtifactMetaOut:
    check_api_key_scope(request, ws_slug)
    return await service.get_artifact_meta(request.app.state.pool, ws_slug, artifact_id)


@router.get(_ART, dependencies=[Depends(require_ws_access)])
async def serve_artifact(
    ws_slug: str,
    artifact_id: uuid.UUID,
    request: Request,
    _: AuthUser = _Auth,
    disposition: str = Query(default="inline", pattern="^(inline|attachment)$"),
) -> Response:
    """Contenu de l'artefact. `disposition=attachment` force le téléchargement."""
    check_api_key_scope(request, ws_slug)
    data, media_type, filename = await service.fetch_artifact_content(
        request.app.state.pool, ws_slug, artifact_id
    )
    return binary_response(data, media_type, filename, attachment=disposition == "attachment")


@router.get(_ART + "/link", dependencies=[Depends(require_ws_access)])
async def mint_artifact_link(
    ws_slug: str, artifact_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> dict[str, object]:
    """Émet un lien signé de courte durée (équivalent REST du tool MCP
    get_artifact_link) : une navigation (nouvel onglet) ne porte pas le
    Bearer — la signature HMAC + expiration portent l'authentification."""
    check_api_key_scope(request, ws_slug)
    # 404 si inconnu — même réponse que les métadonnées, aucun oracle.
    await service.get_artifact_meta(request.app.state.pool, ws_slug, artifact_id)
    settings = request.app.state.settings
    ttl = settings.artifact_link_ttl_seconds
    query = build_download_query(
        ws_slug, artifact_id, ttl_seconds=ttl, secret=settings.jwt_secret.reveal()
    )
    return {
        "url": f"/api/workspaces/{ws_slug}/artifacts/{artifact_id}/download?{query}",
        "expires_in_seconds": ttl,
    }


@router.get(_ART + "/download")
async def download_artifact_signed(
    ws_slug: str,
    artifact_id: uuid.UUID,
    request: Request,
    exp: int = Query(...),
    sig: str = Query(..., min_length=64, max_length=64),
) -> Response:
    """Téléchargement par lien signé (émis par le tool MCP get_artifact_link).

    Pas de Bearer : l'authentification est portée par la signature HMAC
    (workspace + artefact + expiration), vérifiée en temps constant. Le RBAC
    a été appliqué au moment de l'émission du lien.
    """
    secret: str = request.app.state.settings.jwt_secret.reveal()
    if not verify_download_sig(ws_slug, artifact_id, exp, sig, secret=secret):
        # 404 (et non 403) : ne pas confirmer l'existence de l'artefact
        # à un porteur de lien invalide ou expiré.
        raise HTTPException(status_code=404, detail="lien invalide ou expiré")
    data, media_type, filename = await service.fetch_artifact_content(
        request.app.state.pool, ws_slug, artifact_id
    )
    return binary_response(data, media_type, filename, attachment=True)

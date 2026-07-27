from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from docflow.artifacts import service
from docflow.artifacts.links import verify_download_sig
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
    ws_slug: str, file: UploadFile, request: Request, user: AuthUser = _Auth
) -> ArtifactCreatedOut:
    check_api_key_scope(request, ws_slug, write=True)
    data = await file.read()
    return await service.create_artifact(
        request.app.state.pool,
        ws_slug,
        filename=file.filename or "",
        data=data,
        created_by=user.id,
        max_bytes=request.app.state.settings.artifact_max_bytes,
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
    ws_slug: str, artifact_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> Response:
    check_api_key_scope(request, ws_slug)
    data, media_type, filename = await service.fetch_artifact_content(
        request.app.state.pool, ws_slug, artifact_id
    )
    return binary_response(data, media_type, filename, attachment=False)


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

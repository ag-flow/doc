from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from docflow.artifacts import service, uploads
from docflow.artifacts.links import build_download_query, verify_download_sig
from docflow.auth.deps import check_api_key_scope, require_authenticated
from docflow.schemas.artifact import ArtifactCreatedOut, ArtifactListOut, ArtifactMetaOut
from docflow.schemas.auth import AuthUser
from docflow.workspaces.access import require_ws_access

router = APIRouter(tags=["artifacts"])

_WS = "/workspaces/{ws_slug}"
_ART = _WS + "/artifacts/{artifact_id}"
_Auth = Depends(require_authenticated)

# Jeton de ticket d'upload (secrets.token_urlsafe(32) → base64url).
_UPLOAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


def binary_response(data: bytes, media_type: str, filename: str, *, attachment: bool) -> Response:
    # Défense en profondeur : `text/html` (canal maquette, artefacts mutables)
    # n'est JAMAIS servi par les endpoints artefacts génériques — quelle que
    # soit la disposition, et sur toute origine docflow (authentifiée ou /pub).
    # Seul le serveur de preview (origine dédiée, sandbox, CSP) le rend. Cette
    # garde double le denylist du registre (media_types.py).
    if media_type.lower() == "text/html":
        raise HTTPException(status_code=404, detail="artefact introuvable")
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


@router.post(
    _WS + "/artifacts",
    response_model=ArtifactCreatedOut,
    status_code=201,
    dependencies=[Depends(require_ws_access)],
)
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


@router.put("/uploads/{upload_id}")
async def put_upload(upload_id: str, request: Request) -> dict[str, object]:
    """Dépose les octets d'un ticket d'upload (étape 2 de l'upload en deux temps).

    Pas de Bearer : `upload_id` EST la capacité (aléatoire, à usage unique, à
    TTL court). Le plafond de taille est appliqué au FLUX (pas seulement à la
    valeur annoncée) : on coupe la lecture dès qu'il est dépassé, sans bufferiser
    un corps arbitrairement gros. Le serveur vérifie taille annoncée, extension
    au registre et empreinte recalculée avant de ranger quoi que ce soit.
    """
    if not _UPLOAD_ID_RE.match(upload_id):
        raise HTTPException(status_code=404, detail="ticket d'upload introuvable")
    max_bytes: int = request.app.state.settings.artifact_max_bytes
    buffer = bytearray()
    async for chunk in request.stream():
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"fichier trop volumineux (max {max_bytes} octets)",
            )
    return await uploads.store_upload(
        request.app.state.pool, upload_id, bytes(buffer), max_bytes=max_bytes
    )


@router.get(
    _WS + "/artifacts", response_model=ArtifactListOut, dependencies=[Depends(require_ws_access)]
)
async def list_artifacts(
    ws_slug: str,
    request: Request,
    _: AuthUser = _Auth,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    filename: str | None = Query(default=None, description="Nom partiel (insensible à la casse)"),
    sha256: str | None = Query(default=None, pattern="^[0-9a-fA-F]{64}$"),
    document_id: uuid.UUID | None = Query(default=None, description="Référencés par ce document"),
) -> ArtifactListOut:
    """Liste/recherche paginée des artefacts d'un workspace. Filtres optionnels
    combinables : `filename` (partiel), `sha256` (exact), `document_id`
    (référencés par ce document). Renvoie toutes les colonnes (sauf le binaire)
    + refcount."""
    check_api_key_scope(request, ws_slug)
    items, total = await service.list_artifacts(
        request.app.state.pool,
        ws_slug,
        limit=limit,
        offset=offset,
        filename=filename,
        sha256=sha256,
        document_id=document_id,
    )
    return ArtifactListOut(items=items, total=total, limit=limit, offset=offset)


@router.get(
    _ART + "/meta", response_model=ArtifactMetaOut, dependencies=[Depends(require_ws_access)]
)
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

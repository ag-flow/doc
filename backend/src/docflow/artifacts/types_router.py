from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from docflow.artifacts import media_types
from docflow.auth.deps import require_authenticated, require_superadmin
from docflow.schemas.artifact import (
    ArtifactTypeCreate,
    ArtifactTypeOut,
    ArtifactTypeUpdate,
)
from docflow.schemas.auth import AuthUser

# Lecture : tout utilisateur authentifié (l'éditeur propose ces types au
# collage). Écriture : admin uniquement (frontière de sécurité).
read_router = APIRouter(prefix="/artifact-types", tags=["artifact-types"])
admin_router = APIRouter(prefix="/admin/artifact-types", tags=["artifact-types"])

_Auth = Depends(require_authenticated)
_SuperAdmin = Depends(require_superadmin)


@read_router.get("", response_model=list[ArtifactTypeOut])
async def list_artifact_types(request: Request, _: AuthUser = _Auth) -> list[ArtifactTypeOut]:
    rows = await media_types.list_types(request.app.state.pool)
    return [ArtifactTypeOut(**r) for r in rows]


@admin_router.get("", response_model=list[ArtifactTypeOut])
async def admin_list_artifact_types(
    request: Request, _: AuthUser = _SuperAdmin
) -> list[ArtifactTypeOut]:
    rows = await media_types.list_types(request.app.state.pool)
    return [ArtifactTypeOut(**r) for r in rows]


@admin_router.post("", response_model=ArtifactTypeOut, status_code=201)
async def create_artifact_type(
    body: ArtifactTypeCreate, request: Request, _: AuthUser = _SuperAdmin
) -> ArtifactTypeOut:
    row = await media_types.add_type(
        request.app.state.pool,
        extension=body.extension,
        media_type=body.media_type,
        label=body.label,
    )
    return ArtifactTypeOut(**row)


@admin_router.patch("/{extension}", response_model=ArtifactTypeOut)
async def update_artifact_type(
    extension: str, body: ArtifactTypeUpdate, request: Request, _: AuthUser = _SuperAdmin
) -> ArtifactTypeOut:
    row = await media_types.update_type(
        request.app.state.pool, extension, media_type=body.media_type, label=body.label
    )
    return ArtifactTypeOut(**row)


@admin_router.delete("/{extension}", status_code=204)
async def delete_artifact_type(
    extension: str, request: Request, _: AuthUser = _SuperAdmin
) -> None:
    await media_types.delete_type(request.app.state.pool, extension)

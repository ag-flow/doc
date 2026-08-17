from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from docflow.auth.deps import require_authenticated, require_superadmin
from docflow.remote import service
from docflow.remote.probe import probe_connection
from docflow.remote.schemas import (
    RemoteCertificateCreate,
    RemoteCertificateGenerate,
    RemoteCertificateOut,
    RemotePointCreate,
    RemotePointOut,
    RemotePointUpdate,
)

# Superadmin au niveau du ROUTER : un remote point est une destination sortante
# (hôte, clés, certificats) — pouvoir en créer une, c'est pouvoir désigner où
# part une sauvegarde. Protection héritée par toute route ajoutée ensuite.
router = APIRouter(
    prefix="/admin/remote",
    tags=["remote"],
    dependencies=[Depends(require_superadmin)],
)

_Auth = Depends(require_authenticated)


def _fernet(request: Request) -> str | None:
    key = request.app.state.settings.encryption_key
    return key.reveal() if key else None


# ── Certificats ──────────────────────────────────────────────────────────────


@router.get("/certificates", response_model=list[RemoteCertificateOut])
async def list_certificates(request: Request, _: None = _Auth) -> list[RemoteCertificateOut]:
    return await service.list_certificates(request.app.state.pool)


@router.post(
    "/certificates",
    response_model=RemoteCertificateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_certificate(
    body: RemoteCertificateCreate,
    request: Request,
    _: None = _Auth,
) -> RemoteCertificateOut:
    key = _fernet(request)
    if not key:
        from fastapi import HTTPException

        raise HTTPException(422, "encryption_key non configurée")
    return await service.create_certificate(request.app.state.pool, body, key)


@router.post(
    "/certificates/generate",
    response_model=RemoteCertificateOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_certificate(
    body: RemoteCertificateGenerate,
    request: Request,
    _: None = _Auth,
) -> RemoteCertificateOut:
    """Génère une paire de clés SSH ed25519 côté serveur — clé privée jamais exposée."""
    key = _fernet(request)
    if not key:
        from fastapi import HTTPException

        raise HTTPException(422, "encryption_key non configurée")
    return await service.generate_certificate(request.app.state.pool, body, key)


@router.get("/certificates/{slug}", response_model=RemoteCertificateOut)
async def get_certificate(slug: str, request: Request, _: None = _Auth) -> RemoteCertificateOut:
    return await service.get_certificate(request.app.state.pool, slug)


@router.delete("/certificates/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certificate(slug: str, request: Request, _: None = _Auth) -> None:
    await service.delete_certificate(request.app.state.pool, slug)


# ── Remote Points ─────────────────────────────────────────────────────────────


@router.get("/points", response_model=list[RemotePointOut])
async def list_points(request: Request, _: None = _Auth) -> list[RemotePointOut]:
    return await service.list_points(request.app.state.pool)


@router.post(
    "/points",
    response_model=RemotePointOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_point(
    body: RemotePointCreate, request: Request, _: None = _Auth
) -> RemotePointOut:
    return await service.create_point(request.app.state.pool, body, _fernet(request))


@router.get("/points/{slug}", response_model=RemotePointOut)
async def get_point(slug: str, request: Request, _: None = _Auth) -> RemotePointOut:
    return await service.get_point(request.app.state.pool, slug)


@router.put("/points/{slug}", response_model=RemotePointOut)
async def update_point(
    slug: str, body: RemotePointUpdate, request: Request, _: None = _Auth
) -> RemotePointOut:
    return await service.update_point(request.app.state.pool, slug, body, _fernet(request))


@router.delete("/points/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_point(slug: str, request: Request, _: None = _Auth) -> None:
    await service.delete_point(request.app.state.pool, slug)


@router.post("/points/{slug}/test")
async def test_point(slug: str, request: Request, _: None = _Auth) -> dict[str, object]:
    """Teste la connexion du point tel que sauvegardé (pas les valeurs non enregistrées)."""
    return await probe_connection(request.app.state.pool, slug, request.app.state.settings)

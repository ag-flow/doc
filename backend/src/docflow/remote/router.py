from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from docflow.auth.deps import require_admin
from docflow.remote import service
from docflow.remote.schemas import (
    RemoteCertificateCreate,
    RemoteCertificateOut,
    RemotePointCreate,
    RemotePointOut,
    RemotePointUpdate,
)

router = APIRouter(prefix="/admin/remote", tags=["remote"])

_Admin = Depends(require_admin)


def _fernet(request: Request) -> str | None:
    key = request.app.state.settings.encryption_key
    return key.reveal() if key else None


# ── Certificats ──────────────────────────────────────────────────────────────


@router.get("/certificates", response_model=list[RemoteCertificateOut])
async def list_certificates(request: Request, _: None = _Admin) -> list[RemoteCertificateOut]:
    return await service.list_certificates(request.app.state.pool)


@router.post(
    "/certificates",
    response_model=RemoteCertificateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_certificate(
    body: RemoteCertificateCreate,
    request: Request,
    _: None = _Admin,
) -> RemoteCertificateOut:
    key = _fernet(request)
    if not key:
        from fastapi import HTTPException

        raise HTTPException(422, "encryption_key non configurée")
    return await service.create_certificate(request.app.state.pool, body, key)


@router.get("/certificates/{slug}", response_model=RemoteCertificateOut)
async def get_certificate(slug: str, request: Request, _: None = _Admin) -> RemoteCertificateOut:
    return await service.get_certificate(request.app.state.pool, slug)


@router.delete("/certificates/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certificate(slug: str, request: Request, _: None = _Admin) -> None:
    await service.delete_certificate(request.app.state.pool, slug)


# ── Remote Points ─────────────────────────────────────────────────────────────


@router.get("/points", response_model=list[RemotePointOut])
async def list_points(request: Request, _: None = _Admin) -> list[RemotePointOut]:
    return await service.list_points(request.app.state.pool)


@router.post(
    "/points",
    response_model=RemotePointOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_point(
    body: RemotePointCreate, request: Request, _: None = _Admin
) -> RemotePointOut:
    return await service.create_point(request.app.state.pool, body, _fernet(request))


@router.get("/points/{slug}", response_model=RemotePointOut)
async def get_point(slug: str, request: Request, _: None = _Admin) -> RemotePointOut:
    return await service.get_point(request.app.state.pool, slug)


@router.put("/points/{slug}", response_model=RemotePointOut)
async def update_point(
    slug: str, body: RemotePointUpdate, request: Request, _: None = _Admin
) -> RemotePointOut:
    return await service.update_point(request.app.state.pool, slug, body, _fernet(request))


@router.delete("/points/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_point(slug: str, request: Request, _: None = _Admin) -> None:
    await service.delete_point(request.app.state.pool, slug)

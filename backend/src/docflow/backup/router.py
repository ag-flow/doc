from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from docflow.auth.deps import require_admin
from docflow.backup import service
from docflow.backup.schemas import (
    BackupJobCreate,
    BackupJobOut,
    BackupJobRunOut,
    BackupJobUpdate,
)

router = APIRouter(prefix="/admin/backup", tags=["backup"])

_Admin = Depends(require_admin)


@router.get("/jobs", response_model=list[BackupJobOut])
async def list_jobs(request: Request, _: None = _Admin) -> list[BackupJobOut]:
    return await service.list_jobs(request.app.state.pool)


@router.post("/jobs", response_model=BackupJobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: BackupJobCreate, request: Request, _: None = _Admin
) -> BackupJobOut:
    return await service.create_job(request.app.state.pool, body)


@router.get("/jobs/{slug}", response_model=BackupJobOut)
async def get_job(slug: str, request: Request, _: None = _Admin) -> BackupJobOut:
    return await service.get_job(request.app.state.pool, slug)


@router.put("/jobs/{slug}", response_model=BackupJobOut)
async def update_job(
    slug: str, body: BackupJobUpdate, request: Request, _: None = _Admin
) -> BackupJobOut:
    return await service.update_job(request.app.state.pool, slug, body)


@router.delete("/jobs/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(slug: str, request: Request, _: None = _Admin) -> None:
    await service.delete_job(request.app.state.pool, slug)


@router.get("/jobs/{slug}/runs", response_model=list[BackupJobRunOut])
async def list_runs(
    slug: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    _: None = _Admin,
) -> list[BackupJobRunOut]:
    return await service.list_runs(request.app.state.pool, slug, limit)

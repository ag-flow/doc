from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from docflow.auth.deps import require_authenticated
from docflow.backup import runs, service
from docflow.backup.schemas import (
    BackupJobCreate,
    BackupJobOut,
    BackupJobRunOut,
    BackupJobUpdate,
    DumpArchiveOut,
    RestoreGitIn,
    RestoreGitReport,
)

router = APIRouter(prefix="/admin/backup", tags=["backup"])

_Auth = Depends(require_authenticated)


@router.get("/jobs", response_model=list[BackupJobOut])
async def list_jobs(request: Request, _: None = _Auth) -> list[BackupJobOut]:
    return await service.list_jobs(request.app.state.pool)


@router.post("/jobs", response_model=BackupJobOut, status_code=status.HTTP_201_CREATED)
async def create_job(body: BackupJobCreate, request: Request, _: None = _Auth) -> BackupJobOut:
    return await service.create_job(request.app.state.pool, body)


@router.get("/jobs/{slug}", response_model=BackupJobOut)
async def get_job(slug: str, request: Request, _: None = _Auth) -> BackupJobOut:
    return await service.get_job(request.app.state.pool, slug)


@router.put("/jobs/{slug}", response_model=BackupJobOut)
async def update_job(
    slug: str, body: BackupJobUpdate, request: Request, _: None = _Auth
) -> BackupJobOut:
    return await service.update_job(request.app.state.pool, slug, body)


@router.delete("/jobs/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(slug: str, request: Request, _: None = _Auth) -> None:
    await service.delete_job(request.app.state.pool, slug)


@router.get("/jobs/{slug}/archives", response_model=list[DumpArchiveOut])
async def list_archives(slug: str, request: Request, _: None = _Auth) -> list[DumpArchiveOut]:
    return await service.list_job_archives(request.app.state.pool, request.app.state.settings, slug)


@router.get("/jobs/{slug}/runs", response_model=list[BackupJobRunOut])
async def list_runs(
    slug: str,
    request: Request,
    limit: int = Query(default=runs.RUN_RETENTION, ge=1, le=100),
    _: None = _Auth,
) -> list[BackupJobRunOut]:
    return await runs.list_runs(request.app.state.pool, slug, limit)


@router.post(
    "/jobs/{slug}/run",
    response_model=BackupJobRunOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="trigger_backup_job_run",
    summary="Déclenche un run immédiat du job, hors planification",
)
async def trigger_run(slug: str, request: Request, _: None = _Auth) -> BackupJobRunOut:
    """Démarre le run en tâche de fond et répond aussitôt (le push git peut
    dépasser le timeout d'un appelant HTTP synchrone, ex. une automation).
    Le résultat se consulte via GET /jobs/{slug}/runs. 409 si un run est déjà
    en cours pour ce job.

    Endpoint conçu pour être référencé comme opération de contrat OpenAPI
    dans le module Automations (déclenchement d'une sauvegarde git sur
    changement de document, via une clé API dédiée).
    """
    return await runs.trigger_run_now(request.app.state.pool, request.app.state.settings, slug)


@router.post(
    "/restore-git",
    response_model=RestoreGitReport,
    summary="Réalimente l'instance depuis le miroir git d'un remote point",
)
async def restore_git(body: RestoreGitIn, request: Request, _: None = _Auth) -> RestoreGitReport:
    """Clone le dépôt de sauvegarde du remote point et recrée workspaces,
    types, blocs et documents. Additif et idempotent : ne supprime rien ;
    les éléments en échec sont listés dans `errors` sans bloquer le reste."""
    from docflow.backup.restore_remote import restore_from_remote

    report = await restore_from_remote(
        request.app.state.pool,
        request.app.state.settings,
        remote_point_slug=body.remote_point_slug,
        git_base_path=body.git_base_path,
        workspace=body.workspace,
    )
    return RestoreGitReport(
        workspaces_created=report.workspaces_created,
        blocks_created=report.blocks_created,
        types_imported=report.types_imported,
        docs_created=report.docs_created,
        docs_updated=report.docs_updated,
        errors=report.errors,
    )

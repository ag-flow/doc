from __future__ import annotations

import pathlib

import structlog
import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from docflow.auth.deps import require_admin
from docflow.templates.importer import ImportConflictError, VersionConflictError, run_import
from docflow.templates.inheritance import resolve
from docflow.templates.models import Template

log = structlog.get_logger(__name__)

_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent.parent.parent / "templates"

router = APIRouter(tags=["templates"])

_Admin = Depends(require_admin)


class TemplateInfo(BaseModel):
    template: str
    label: str
    version: int
    path: str
    concrete_types: int
    type_slugs: list[str]


class ImportTemplateIn(BaseModel):
    model_config = {"extra": "forbid"}

    template: str
    dry_run: bool = False


class ImportResultOut(BaseModel):
    applied: bool
    no_op: bool
    adds: int
    soft_updates: int


def load_templates(templates_dir: pathlib.Path) -> list[TemplateInfo]:
    """Scanne templates_dir/*.yaml, ignore les fichiers illisibles/invalides."""
    result: list[TemplateInfo] = []
    if not templates_dir.exists():
        return result
    for yaml_file in sorted(templates_dir.glob("*.yaml")):
        try:
            with yaml_file.open() as f:
                raw = yaml.safe_load(f)
            tpl = Template.model_validate(raw)
            resolved = resolve(tpl)
            result.append(
                TemplateInfo(
                    template=tpl.template,
                    label=tpl.label,
                    version=tpl.version,
                    path=yaml_file.name,
                    concrete_types=len(resolved),
                    type_slugs=[r.slug for r in resolved],
                )
            )
        except Exception:
            log.warning("template_load_error", file=yaml_file.name, exc_info=True)
    return result


def _find_template_file(template_slug: str) -> pathlib.Path:
    for yaml_file in _TEMPLATES_DIR.glob("*.yaml"):
        try:
            with yaml_file.open() as f:
                raw = yaml.safe_load(f)
            tpl = Template.model_validate(raw)
            if tpl.template == template_slug:
                return yaml_file
        except Exception:
            continue
    raise HTTPException(status_code=404, detail=f"template '{template_slug}' introuvable")


@router.get("/templates", response_model=list[TemplateInfo])
async def list_templates() -> list[TemplateInfo]:
    return load_templates(_TEMPLATES_DIR)


@router.post(
    "/workspaces/{ws_slug}/templates/import",
    response_model=ImportResultOut,
)
async def import_template(
    ws_slug: str,
    body: ImportTemplateIn,
    request: Request,
    _: None = _Admin,
) -> ImportResultOut:
    yaml_file = _find_template_file(body.template)
    with yaml_file.open() as f:
        raw = yaml.safe_load(f)
    tpl = Template.model_validate(raw)
    pool = request.app.state.pool
    try:
        report = await run_import(pool, ws_slug, tpl, dry_run=body.dry_run)
    except VersionConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ImportConflictError as e:
        conflicts = [{"path": i.path, "detail": i.detail} for i in e.diff.conflicts]
        raise HTTPException(
            status_code=422,
            detail={"message": "conflits bloquants", "conflicts": conflicts},
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ImportResultOut(
        applied=report.applied,
        no_op=report.no_op,
        adds=len(report.diff.adds),
        soft_updates=len(report.diff.soft_updates),
    )

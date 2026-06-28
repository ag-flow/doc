from __future__ import annotations

import pathlib
import uuid as _uuid

import structlog
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, HttpUrl

from docflow.auth.deps import require_admin
from docflow.templates.gallery import GalleryError, RemoteTemplateData, fetch_gallery, pull_template
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


class TemplateYamlBody(BaseModel):
    model_config = {"extra": "forbid"}
    yaml_content: str


class ImportTemplateIn(BaseModel):
    model_config = {"extra": "forbid"}

    template: str
    dry_run: bool = False


class ImportResultOut(BaseModel):
    applied: bool
    no_op: bool
    adds: int
    soft_updates: int


class RemoteTemplateInfo(BaseModel):
    template: str
    label: str
    version: int
    type_slugs: list[str]
    concrete_types: int
    installed: bool
    update_available: bool


class GalleryConfigOut(BaseModel):
    default_url: str | None


class GalleryPullIn(BaseModel):
    model_config = {"extra": "forbid"}

    source_url: str
    template_slug: str


class GallerySourceIn(BaseModel):
    model_config = {"extra": "forbid"}

    label: str
    url: HttpUrl


class GallerySourceOut(BaseModel):
    id: _uuid.UUID | None  # None = source "builtin" issue de l'env
    label: str
    url: str
    builtin: bool = False


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


# ── Galerie distante ────────────────────────────────────────────────────────
# Ces routes sont déclarées AVANT les routes paramétriques ({template_slug})
# pour éviter toute capture ambiguë.

# -- Sources enregistrées --


@router.get("/templates/gallery/sources", response_model=list[GallerySourceOut])
async def list_gallery_sources(
    request: Request,
    _: None = _Admin,
) -> list[GallerySourceOut]:
    """Liste les sources de galerie enregistrées + la source env si non dupliquée."""
    pool = request.app.state.pool
    rows = await pool.fetch(
        "SELECT id, label, url FROM gallery_source ORDER BY created_at"
    )
    result: list[GallerySourceOut] = [
        GallerySourceOut(id=row["id"], label=row["label"], url=row["url"])
        for row in rows
    ]
    default_url = request.app.state.settings.gallery_url
    if default_url and not any(s.url == default_url for s in result):
        result.insert(0, GallerySourceOut(id=None, label="(défaut)", url=default_url, builtin=True))
    return result


@router.post("/templates/gallery/sources", response_model=GallerySourceOut, status_code=201)
async def add_gallery_source(
    body: GallerySourceIn,
    request: Request,
    _: None = _Admin,
) -> GallerySourceOut:
    pool = request.app.state.pool
    url_str = str(body.url)
    try:
        row = await pool.fetchrow(
            "INSERT INTO gallery_source (label, url) VALUES ($1, $2)"
            " ON CONFLICT (url) DO UPDATE SET label = EXCLUDED.label"
            " RETURNING id, label, url",
            body.label,
            url_str,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    assert row is not None
    log.info("gallery_source_added", url=url_str)
    return GallerySourceOut(id=row["id"], label=row["label"], url=row["url"])


@router.delete("/templates/gallery/sources/{source_id}", status_code=204)
async def delete_gallery_source(
    source_id: _uuid.UUID,
    request: Request,
    _: None = _Admin,
) -> None:
    pool = request.app.state.pool
    deleted = await pool.fetchval(
        "DELETE FROM gallery_source WHERE id = $1 RETURNING id", source_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="source introuvable")
    log.info("gallery_source_deleted", id=str(source_id))


# -- Config & fetch --


@router.get("/templates/gallery/config", response_model=GalleryConfigOut)
async def gallery_config(
    request: Request,
    _: None = _Admin,
) -> GalleryConfigOut:
    """Retourne l'URL de galerie configurée dans l'env (GALLERY_URL), ou null."""
    return GalleryConfigOut(default_url=request.app.state.settings.gallery_url)


@router.get("/templates/gallery", response_model=list[RemoteTemplateInfo])
async def list_gallery(
    source_url: str = Query(..., description="URL de base de la galerie distante"),
    _: None = _Admin,
) -> list[RemoteTemplateInfo]:
    """Lit toc.txt + les YAMLs distants et les compare aux templates locaux."""
    try:
        remote = await fetch_gallery(source_url)
    except GalleryError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    local: dict[str, TemplateInfo] = {t.template: t for t in load_templates(_TEMPLATES_DIR)}

    result: list[RemoteTemplateInfo] = []
    r: RemoteTemplateData
    for r in remote:
        loc = local.get(r["template"])
        result.append(
            RemoteTemplateInfo(
                template=r["template"],
                label=r["label"],
                version=r["version"],
                type_slugs=r["type_slugs"],
                concrete_types=r["concrete_types"],
                installed=loc is not None,
                update_available=loc is not None and loc.version < r["version"],
            )
        )
    return result


@router.post("/templates/gallery/pull", response_model=TemplateInfo)
async def pull_from_gallery(
    body: GalleryPullIn,
    _: None = _Admin,
) -> TemplateInfo:
    """Télécharge un template depuis la galerie et le sauvegarde localement."""
    try:
        tpl = await pull_template(body.source_url, body.template_slug, _TEMPLATES_DIR)
    except GalleryError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Template invalide : {e}") from e

    resolved = resolve(tpl)
    return TemplateInfo(
        template=tpl.template,
        label=tpl.label,
        version=tpl.version,
        path=f"{tpl.template}.yaml",
        concrete_types=len(resolved),
        type_slugs=[r.slug for r in resolved],
    )


# ── Templates locaux (CRUD) ─────────────────────────────────────────────────


@router.get("/templates/{template_slug}/yaml", response_class=PlainTextResponse)
async def get_template_yaml(
    template_slug: str,
    _: None = _Admin,
) -> str:
    yaml_file = _find_template_file(template_slug)
    return yaml_file.read_text()


@router.put("/templates/{template_slug}/yaml", response_model=TemplateInfo)
async def update_template_yaml(
    template_slug: str,
    body: TemplateYamlBody,
    _: None = _Admin,
) -> TemplateInfo:
    try:
        raw = yaml.safe_load(body.yaml_content)
        tpl = Template.model_validate(raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"YAML invalide : {e}") from e
    if tpl.template != template_slug:
        raise HTTPException(
            status_code=422,
            detail=(
                f"le slug dans le YAML ({tpl.template!r}) "
                f"doit correspondre à celui de l'URL ({template_slug!r})"
            ),
        )
    yaml_file = _find_template_file(template_slug)
    yaml_file.write_text(body.yaml_content)
    log.info("template_updated", template=template_slug, version=tpl.version)
    resolved = resolve(tpl)
    return TemplateInfo(
        template=tpl.template,
        label=tpl.label,
        version=tpl.version,
        path=yaml_file.name,
        concrete_types=len(resolved),
        type_slugs=[r.slug for r in resolved],
    )


@router.delete("/templates/{template_slug}", status_code=204)
async def delete_template(
    template_slug: str,
    _: None = _Admin,
) -> None:
    yaml_file = _find_template_file(template_slug)
    yaml_file.unlink()
    log.info("template_deleted", template=template_slug)


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

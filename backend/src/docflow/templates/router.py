from __future__ import annotations

import json
import pathlib
import re
import uuid as _uuid

import structlog
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, HttpUrl, field_validator

from docflow.auth.deps import require_api_key_admin_write, require_authenticated
from docflow.templates.gallery import (
    GalleryError,
    RemoteTemplateData,
    fetch_gallery,
    fetch_template,
    pull_template,
)
from docflow.templates.importer import ImportConflictError, VersionConflictError, run_import
from docflow.templates.inheritance import resolve
from docflow.templates.models import Template
from docflow.workspaces.access import require_ws_access

log = structlog.get_logger(__name__)

_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent.parent.parent / "templates"

# Même regex que `remote/schemas.py::_SLUG_RE` / `templates/gallery.py::_SLUG_RE`.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")

router = APIRouter(tags=["templates"])

_Auth = Depends(require_authenticated)


class TemplateInfo(BaseModel):
    template: str
    label: str
    version: int
    path: str
    concrete_types: int
    type_slugs: list[str]
    # Blocs utilisateurs (tous workspaces) portés par les types de ce template.
    blocks_count: int = 0


class TemplateYamlBody(BaseModel):
    model_config = {"extra": "forbid"}
    yaml_content: str


class ImportTemplateIn(BaseModel):
    model_config = {"extra": "forbid"}

    template: str
    dry_run: bool = False


class TemplateUploadIn(BaseModel):
    model_config = {"extra": "forbid"}

    yaml_content: str


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

    @field_validator("template_slug")
    @classmethod
    def _validate_template_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("template_slug : minuscules, chiffres, tirets, 2-80 chars")
        return v


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


# Blocs (tous workspaces) portés par un type issu de chaque template — le
# listing annonce l'usage réel, la suppression s'appuie sur la même requête.
_BLOCKS_BY_TEMPLATE = """
SELECT ft.source_template, w.slug AS ws_slug, b.label
FROM data_block b
JOIN functional_type ft ON ft.id = b.functional_type_ref
JOIN workspace w ON w.workspace_technical_key = b.workspace_technical_key
WHERE ft.source_template IS NOT NULL
ORDER BY w.slug, b.label
"""


@router.get("/templates", response_model=list[TemplateInfo])
async def list_templates(request: Request) -> list[TemplateInfo]:
    templates = load_templates(_TEMPLATES_DIR)
    rows = await request.app.state.pool.fetch(_BLOCKS_BY_TEMPLATE)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["source_template"]] = counts.get(r["source_template"], 0) + 1
    for tpl in templates:
        tpl.blocks_count = counts.get(tpl.template, 0)
    return templates


# ── Galerie distante ────────────────────────────────────────────────────────
# Ces routes sont déclarées AVANT les routes paramétriques ({template_slug})
# pour éviter toute capture ambiguë.

# -- Sources enregistrées --


@router.get("/templates/gallery/sources", response_model=list[GallerySourceOut])
async def list_gallery_sources(
    request: Request,
    _: None = _Auth,
) -> list[GallerySourceOut]:
    """Liste les sources de galerie enregistrées + la source env si non dupliquée."""
    pool = request.app.state.pool
    rows = await pool.fetch("SELECT id, label, url FROM gallery_source ORDER BY created_at")
    result: list[GallerySourceOut] = [
        GallerySourceOut(id=row["id"], label=row["label"], url=row["url"]) for row in rows
    ]
    default_url = request.app.state.settings.gallery_url
    if default_url and not any(s.url == default_url for s in result):
        result.insert(0, GallerySourceOut(id=None, label="(défaut)", url=default_url, builtin=True))
    return result


@router.post("/templates/gallery/sources", response_model=GallerySourceOut, status_code=201)
async def add_gallery_source(
    body: GallerySourceIn,
    request: Request,
    _: None = _Auth,
) -> GallerySourceOut:
    pool = request.app.state.pool
    url_str = str(body.url)
    exists = await pool.fetchval("SELECT 1 FROM gallery_source WHERE url = $1", url_str)
    if exists:
        raise HTTPException(status_code=409, detail="cette source est déjà enregistrée")
    try:
        row = await pool.fetchrow(
            "INSERT INTO gallery_source (label, url) VALUES ($1, $2) RETURNING id, label, url",
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
    _: None = _Auth,
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
    _: None = _Auth,
) -> GalleryConfigOut:
    """Retourne l'URL de galerie configurée dans l'env (GALLERY_URL), ou null."""
    return GalleryConfigOut(default_url=request.app.state.settings.gallery_url)


@router.get("/templates/gallery", response_model=list[RemoteTemplateInfo])
async def list_gallery(
    source_url: str = Query(..., description="URL de base de la galerie distante"),
    _: None = _Auth,
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


class GalleryPullDiffOut(BaseModel):
    template: str
    installed_version: int | None
    remote_version: int
    new_types: list[str]
    # Propriétés ajoutées aux types déjà installés : « type.prop ».
    new_properties: list[str]


@router.post("/templates/gallery/pull/diff", response_model=GalleryPullDiffOut)
async def diff_gallery_pull(
    body: GalleryPullIn,
    _: None = _Auth,
) -> GalleryPullDiffOut:
    """Ce que la mise à jour changerait — AVANT de confirmer (aucune écriture)."""
    try:
        remote_tpl = await fetch_template(body.source_url, body.template_slug)
    except GalleryError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Template invalide : {e}") from e

    remote_types = {r.slug: r for r in resolve(remote_tpl)}
    local = {t.template: t for t in load_templates(_TEMPLATES_DIR)}.get(body.template_slug)
    local_types: dict[str, set[str]] = {}
    installed_version: int | None = None
    if local is not None:
        installed_version = local.version
        yaml_file = _find_template_file(body.template_slug)
        with yaml_file.open() as f:
            local_tpl = Template.model_validate(yaml.safe_load(f))
        for r in resolve(local_tpl):
            local_types[r.slug] = {p.slug for p in r.properties}

    new_types = sorted(slug for slug in remote_types if slug not in local_types)
    new_properties = sorted(
        f"{slug}.{p.slug}"
        for slug, r in remote_types.items()
        if slug in local_types
        for p in r.properties
        if p.slug not in local_types[slug]
    )
    return GalleryPullDiffOut(
        template=body.template_slug,
        installed_version=installed_version,
        remote_version=remote_tpl.version,
        new_types=new_types,
        new_properties=new_properties,
    )


@router.post("/templates/gallery/pull", response_model=TemplateInfo)
async def pull_from_gallery(
    body: GalleryPullIn,
    _: None = _Auth,
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
    _: None = _Auth,
) -> str:
    yaml_file = _find_template_file(template_slug)
    return yaml_file.read_text()


@router.get("/templates/{template_slug}/export")
async def export_template(template_slug: str, _: None = _Auth) -> Response:
    """Export APLATI du template (héritage résolu), en JSON téléchargeable.

    Snapshot fidèle de l'état une fois l'héritage résolu — tel qu'il vit après
    import : chaque type concret (les `abstract` exclus) porte toutes ses
    propriétés directement, et son `parent` (hiérarchie). Ce n'est pas un
    aller-retour mécanique : reconstruire l'héritage à partir de l'export est un
    travail d'interprétation (cf. fiche 45d5da21).
    """
    yaml_file = _find_template_file(template_slug)
    try:
        tpl = Template.model_validate(yaml.safe_load(yaml_file.read_text()))
        resolved = resolve(tpl)
    except HTTPException:
        raise
    except Exception as e:  # YAML illisible / héritage incohérent → 422 explicite
        raise HTTPException(status_code=422, detail=f"template non résolvable : {e}") from e

    payload = {
        "template": tpl.template,
        "label": tpl.label,
        "version": tpl.version,
        "functional_types": [r.model_dump(mode="json") for r in resolved],
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{tpl.template}.json"'},
    )


@router.post("/templates", response_model=TemplateInfo, status_code=201)
async def create_template_from_upload(
    body: TemplateUploadIn,
    _: None = _Auth,
) -> TemplateInfo:
    """Installe un nouveau template global depuis un payload YAML uploadé.

    Le payload est le modèle NATIF (héritage non résolu, tel qu'il vit dans un
    repo source). Il est validé, puis résolu pour vérifier la cohérence de
    l'héritage, puis persisté dans le répertoire des templates globaux — il
    devient dès lors importable comme les autres (list_templates, galerie,
    import_template). Création seule : si un template porte déjà ce slug, le
    mettre à jour via PUT /templates/{slug}/yaml (409 sinon).
    """
    try:
        raw = yaml.safe_load(body.yaml_content)
        tpl = Template.model_validate(raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"YAML invalide : {e}") from e
    if not _SLUG_RE.match(tpl.template):
        raise HTTPException(
            status_code=422,
            detail="slug de template invalide : minuscules, chiffres, tirets, 2-80 chars",
        )
    try:
        resolved = resolve(tpl)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"héritage non résolvable : {e}") from e

    # Création uniquement : ni un template de même slug (repéré par contenu), ni un
    # fichier de même nom ne doivent être écrasés en douce par un upload.
    for existing in _TEMPLATES_DIR.glob("*.yaml"):
        try:
            other = Template.model_validate(yaml.safe_load(existing.read_text()))
        except Exception:
            continue
        if other.template == tpl.template:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"un template '{tpl.template}' est déjà installé ; "
                    "utiliser PUT /templates/{slug}/yaml pour le mettre à jour"
                ),
            )

    yaml_file = _TEMPLATES_DIR / f"{tpl.template}.yaml"
    if yaml_file.exists():
        raise HTTPException(
            status_code=409,
            detail=f"un fichier de template '{yaml_file.name}' existe déjà",
        )
    _TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    yaml_file.write_text(body.yaml_content)
    log.info("template_installed_from_upload", template=tpl.template, version=tpl.version)
    return TemplateInfo(
        template=tpl.template,
        label=tpl.label,
        version=tpl.version,
        path=yaml_file.name,
        concrete_types=len(resolved),
        type_slugs=[r.slug for r in resolved],
    )


@router.put("/templates/{template_slug}/yaml", response_model=TemplateInfo)
async def update_template_yaml(
    template_slug: str,
    body: TemplateYamlBody,
    _: None = _Auth,
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
    request: Request,
    _: None = _Auth,
) -> None:
    yaml_file = _find_template_file(template_slug)
    # Refus motivé : des blocs (dans n'importe quel workspace) reposent sur les
    # types de ce template — la liste est retournée, pas seulement un compte.
    rows = await request.app.state.pool.fetch(
        "SELECT w.slug AS ws_slug, b.label FROM data_block b "
        "JOIN functional_type ft ON ft.id = b.functional_type_ref "
        "JOIN workspace w ON w.workspace_technical_key = b.workspace_technical_key "
        "WHERE ft.source_template = $1 ORDER BY w.slug, b.label",
        template_slug,
    )
    if rows:
        blocks = [f"{r['ws_slug']} / {r['label']}" for r in rows]
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"template utilisé par {len(blocks)} bloc(s)",
                "blocks": blocks,
            },
        )
    yaml_file.unlink()
    log.info("template_deleted", template=template_slug)


@router.post(
    "/workspaces/{ws_slug}/templates/import",
    dependencies=[Depends(require_ws_access)],
    response_model=ImportResultOut,
)
async def import_template(
    ws_slug: str,
    body: ImportTemplateIn,
    request: Request,
    _: None = _Auth,
) -> ImportResultOut:
    require_api_key_admin_write(request)
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

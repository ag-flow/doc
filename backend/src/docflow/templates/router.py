from __future__ import annotations

import pathlib

import structlog
import yaml
from fastapi import APIRouter
from pydantic import BaseModel

from docflow.templates.inheritance import resolve
from docflow.templates.models import Template

log = structlog.get_logger(__name__)

_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent.parent.parent / "templates"

router = APIRouter(tags=["templates"])


class TemplateInfo(BaseModel):
    template: str
    label: str
    version: int
    path: str
    concrete_types: int
    type_slugs: list[str]


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
            result.append(TemplateInfo(
                template=tpl.template,
                label=tpl.label,
                version=tpl.version,
                path=yaml_file.name,
                concrete_types=len(resolved),
                type_slugs=[r.slug for r in resolved],
            ))
        except Exception:
            log.warning("template_load_error", file=yaml_file.name, exc_info=True)
    return result


@router.get("/templates", response_model=list[TemplateInfo])
async def list_templates() -> list[TemplateInfo]:
    return load_templates(_TEMPLATES_DIR)

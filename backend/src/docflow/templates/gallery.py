from __future__ import annotations

import asyncio
import pathlib
from typing import TypedDict

import httpx
import structlog
import yaml

from docflow.templates.inheritance import resolve
from docflow.templates.models import Template

log = structlog.get_logger(__name__)

_TIMEOUT = 15.0


class GalleryError(Exception):
    pass


class RemoteTemplateData(TypedDict):
    template: str
    label: str
    version: int
    type_slugs: list[str]
    concrete_types: int


async def _fetch(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.get(url, timeout=_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPStatusError as e:
        raise GalleryError(f"HTTP {e.response.status_code} sur {url}") from e
    except httpx.RequestError as e:
        raise GalleryError(f"Impossible de contacter {url} : {e}") from e


def _parse_tpl(yaml_text: str) -> tuple[Template, list[str]]:
    raw = yaml.safe_load(yaml_text)
    tpl = Template.model_validate(raw)
    resolved = resolve(tpl)
    return tpl, [r.slug for r in resolved]


async def _fetch_one(
    client: httpx.AsyncClient, base: str, slug: str
) -> RemoteTemplateData | None:
    try:
        yaml_text = await _fetch(client, f"{base}/{slug}.yaml")
        tpl, type_slugs = _parse_tpl(yaml_text)
        return RemoteTemplateData(
            template=tpl.template,
            label=tpl.label,
            version=tpl.version,
            type_slugs=type_slugs,
            concrete_types=len(type_slugs),
        )
    except Exception:
        log.warning("gallery_template_fetch_error", slug=slug, exc_info=True)
        return None


async def fetch_gallery(source_url: str) -> list[RemoteTemplateData]:
    """Lit toc.txt puis charge les métadonnées de chaque template en parallèle."""
    base = source_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        toc = await _fetch(client, f"{base}/toc.txt")
        slugs = [
            line.strip()
            for line in toc.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        results = await asyncio.gather(*[_fetch_one(client, base, s) for s in slugs])
    return [r for r in results if r is not None]


async def pull_template(
    source_url: str, template_slug: str, templates_dir: pathlib.Path
) -> Template:
    """Télécharge un template YAML et le sauvegarde dans templates_dir."""
    base = source_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        yaml_text = await _fetch(client, f"{base}/{template_slug}.yaml")

    # Valider avant d'écrire
    raw = yaml.safe_load(yaml_text)
    tpl = Template.model_validate(raw)

    dest = templates_dir / f"{template_slug}.yaml"
    dest.write_text(yaml_text, encoding="utf-8")
    log.info("gallery_template_pulled", template=template_slug, version=tpl.version)
    return tpl

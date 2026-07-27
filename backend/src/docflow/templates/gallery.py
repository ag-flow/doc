from __future__ import annotations

import asyncio
import pathlib
import re
from typing import TypedDict

import httpx
import structlog
import yaml

from docflow.net.ssrf import SSRFError, validate_public_url
from docflow.templates.inheritance import resolve
from docflow.templates.models import Template

log = structlog.get_logger(__name__)

_TIMEOUT = 15.0

# Même regex que `remote/schemas.py::_SLUG_RE` — un slug de template ne doit
# jamais pouvoir contenir de séparateur de chemin (`/`, `..`, etc.).
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")


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
        await validate_public_url(url)
        # follow_redirects=False : une redirection pourrait viser un hôte interne
        # non revalidé (contournement SSRF). Une source de galerie sert du contenu
        # statique en raw HTTP ; suivre les redirections n'est pas nécessaire.
        resp = await client.get(url, timeout=_TIMEOUT, follow_redirects=False)
        resp.raise_for_status()
        return resp.text
    except SSRFError as e:
        raise GalleryError(f"URL refusée : {e}") from e
    except httpx.HTTPStatusError as e:
        raise GalleryError(f"HTTP {e.response.status_code} sur {url}") from e
    except httpx.RequestError as e:
        raise GalleryError(f"Impossible de contacter {url} : {e}") from e


def _parse_tpl(yaml_text: str) -> tuple[Template, list[str]]:
    raw = yaml.safe_load(yaml_text)
    tpl = Template.model_validate(raw)
    resolved = resolve(tpl)
    return tpl, [r.slug for r in resolved]


async def _fetch_one(client: httpx.AsyncClient, base: str, slug: str) -> RemoteTemplateData | None:
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
            line.strip() for line in toc.splitlines() if line.strip() and not line.startswith("#")
        ]
        results = await asyncio.gather(*[_fetch_one(client, base, s) for s in slugs])
    return [r for r in results if r is not None]


async def fetch_template(source_url: str, template_slug: str) -> Template:
    """Télécharge et valide un template YAML SANS l'écrire (dry-run / diff)."""
    if not _SLUG_RE.match(template_slug):
        raise ValueError(f"template_slug invalide : {template_slug!r}")
    base = source_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        yaml_text = await _fetch(client, f"{base}/{template_slug}.yaml")
    raw = yaml.safe_load(yaml_text)
    tpl = Template.model_validate(raw)
    if tpl.template != template_slug:
        raise ValueError(
            f"le slug du YAML téléchargé ({tpl.template!r}) ne correspond pas "
            f"au slug demandé ({template_slug!r})"
        )
    return tpl


async def pull_template(
    source_url: str, template_slug: str, templates_dir: pathlib.Path
) -> Template:
    """Télécharge un template YAML et le sauvegarde dans templates_dir."""
    if not _SLUG_RE.match(template_slug):
        raise ValueError(f"template_slug invalide : {template_slug!r}")

    base = source_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        yaml_text = await _fetch(client, f"{base}/{template_slug}.yaml")

    # Valider avant d'écrire
    raw = yaml.safe_load(yaml_text)
    tpl = Template.model_validate(raw)
    if tpl.template != template_slug:
        raise ValueError(
            f"le slug du YAML téléchargé ({tpl.template!r}) ne correspond pas "
            f"au slug demandé ({template_slug!r})"
        )

    templates_dir.mkdir(parents=True, exist_ok=True)
    dest = templates_dir / f"{template_slug}.yaml"
    dest.write_text(yaml_text, encoding="utf-8")
    log.info("gallery_template_pulled", template=template_slug, version=tpl.version)
    return tpl

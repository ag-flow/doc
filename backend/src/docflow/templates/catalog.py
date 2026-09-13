"""Catalogue des templates globaux (fichiers YAML du dépôt).

Point d'accès UNIQUE pour retrouver un Template par son slug, partagé par la
surface MCP, le service et le routeur — au lieu d'un scan dupliqué par transport.
"""

from __future__ import annotations

import pathlib

import yaml

from docflow.templates.models import Template

# <repo>/templates — même emplacement que le routeur REST et la passerelle MCP.
TEMPLATES_DIR = pathlib.Path(__file__).parent.parent.parent.parent / "templates"


def find_template(template_slug: str) -> Template:
    """Charge le Template portant ce slug depuis le répertoire global.

    Lève `ValueError` si aucun ne correspond (fichier absent, illisible ou slug
    inconnu) — l'appelant le traduit en 404."""
    if TEMPLATES_DIR.exists():
        for yaml_file in sorted(TEMPLATES_DIR.glob("*.yaml")):
            try:
                with yaml_file.open() as f:
                    raw = yaml.safe_load(f)
                tpl = Template.model_validate(raw)
            except Exception:
                continue
            if tpl.template == template_slug:
                return tpl
    raise ValueError(f"template '{template_slug}' introuvable")

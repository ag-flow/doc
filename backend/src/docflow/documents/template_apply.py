"""Substitution des variables de template de contenu (spec 35 — MTPL)."""
from __future__ import annotations

import re

# Variables reconnues : {{title}} et {{date}}
_VARIABLE_RE = re.compile(r"\{\{(\w+)\}\}")


def apply_content_template(template: str, title: str, today_iso: str) -> str:
    """Résout {{title}} et {{date}} dans template.

    Substitution littérale et sûre : le markdown est du texte brut,
    pas d'injection dans une structure sensible.
    """
    _vars = {"title": title, "date": today_iso}

    def _replace(m: re.Match[str]) -> str:
        return _vars.get(m.group(1), m.group(0))

    return _VARIABLE_RE.sub(_replace, template)

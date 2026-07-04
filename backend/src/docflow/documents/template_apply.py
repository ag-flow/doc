"""Substitution des variables de template de contenu (spec 35 — MTPL)."""
from __future__ import annotations

import datetime
import re
import uuid

import asyncpg

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


async def compute_initial_content(
    conn: asyncpg.Connection,
    ft_id: uuid.UUID | None,
    title: str,
    provided: str | None = None,
) -> str | None:
    """Contenu initial d'un document : contenu fourni sinon template du type appliqué.

    Factorise l'application du content_template pour les deux chemins de création
    (create_document et create_document_in_block) — DOC-14 #1.
    """
    if provided:
        return provided
    if ft_id is None:
        return provided
    template = await conn.fetchval(
        "SELECT content_template FROM functional_type WHERE id = $1", ft_id
    )
    if template:
        today = datetime.date.today().isoformat()
        return apply_content_template(template, title, today)
    return provided

"""Tests MTPL — templates de contenu (spec 35)."""
from __future__ import annotations

import asyncpg
import pytest

from docflow.documents.template_apply import apply_content_template


# ── Moteur de substitution (sans DB) ─────────────────────────────────────────

def test_substitution_title_and_date() -> None:
    tpl = "# {{title}}\n> Créé le {{date}}"
    result = apply_content_template(tpl, "Ma feature", "2026-06-28")
    assert result == "# Ma feature\n> Créé le 2026-06-28"


def test_substitution_no_variables() -> None:
    tpl = "## Contexte\n## Objectif"
    result = apply_content_template(tpl, "Doc", "2026-06-28")
    assert result == tpl


def test_substitution_unknown_variable_kept() -> None:
    tpl = "{{unknown}} and {{title}}"
    result = apply_content_template(tpl, "X", "2026-06-28")
    assert result == "{{unknown}} and X"


def test_substitution_title_with_markdown_chars() -> None:
    tpl = "# {{title}}"
    result = apply_content_template(tpl, "Title with **bold** & [link](url)", "2026-01-01")
    assert "Title with **bold** & [link](url)" in result


# ── Application à la création (DB) ───────────────────────────────────────────

async def test_template_applied_on_empty_body(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """Corps vide + template → pré-rempli."""
    from docflow.schemas.types import FunctionalTypeCreate, FunctionalTypeUpdate
    from docflow.schemas.document import DocumentCreate
    from docflow.types import service as type_svc
    from docflow.documents import service as doc_svc

    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="t35a", label="T35A"))
    await type_svc.update_type(
        db_pool, ws, "t35a",
        FunctionalTypeUpdate(content_template="# {{title}}\n> {{date}}"),
    )

    doc = await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(title="Ma feature", parent_id=None, functional_type_slug="t35a"),
    )
    assert doc.content is not None
    assert "Ma feature" in doc.content
    assert "{{title}}" not in doc.content  # variables résolues


async def test_template_not_applied_on_provided_body(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Corps fourni → template ignoré (pas d'écrasement)."""
    from docflow.schemas.types import FunctionalTypeCreate, FunctionalTypeUpdate
    from docflow.schemas.document import DocumentCreate
    from docflow.types import service as type_svc
    from docflow.documents import service as doc_svc

    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="t35b", label="T35B"))
    await type_svc.update_type(
        db_pool, ws, "t35b",
        FunctionalTypeUpdate(content_template="# {{title}}"),
    )

    doc = await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(
            title="Feature",
            parent_id=None,
            functional_type_slug="t35b",
            content="Mon brouillon personnel",
        ),
    )
    assert doc.content == "Mon brouillon personnel"


async def test_existing_docs_unaffected_by_template_change(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Modifier le modèle n'altère pas les documents déjà créés."""
    from docflow.schemas.types import FunctionalTypeCreate, FunctionalTypeUpdate
    from docflow.schemas.document import DocumentCreate
    from docflow.types import service as type_svc
    from docflow.documents import service as doc_svc

    ws = "test-ws"
    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="t35c", label="T35C"))
    # Pas de template initialement
    doc = await doc_svc.create_document(
        db_pool, ws,
        DocumentCreate(title="Old doc", parent_id=None, functional_type_slug="t35c"),
    )
    # Ajouter un template après coup
    await type_svc.update_type(
        db_pool, ws, "t35c",
        FunctionalTypeUpdate(content_template="# {{title}}\n## Contexte"),
    )
    # Le document existant est inchangé
    retrieved = await doc_svc.get_document(db_pool, ws, doc.doc_technical_key)
    assert retrieved.content is None or "Contexte" not in (retrieved.content or "")

"""`content_template` d'un type : résolution, import, diff et export.

`TypeDef.content_template` (spec MEXP) était accepté dans le YAML puis jeté à la
résolution d'héritage — jamais écrit dans `functional_type.content_template`,
jamais comparé par le diff, absent de l'export.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import pytest

from docflow.schemas.workspace import WorkspaceCreate
from docflow.templates.importer import run_import
from docflow.templates.inheritance import resolve
from docflow.templates.models import PropDef, Template, TypeDef
from docflow.workspaces import service as ws_svc

_TEMPLATE_SLUG = "ct-test"
_BODY = "# {{title}}\n\n## Contexte"


def _tpl(version: int, *, content_template: str | None, label: str = "Epic") -> Template:
    return Template(
        version=version,
        template=_TEMPLATE_SLUG,
        label="CT Test",
        functional_types=[
            TypeDef(
                slug="epic",
                label=label,
                content_template=content_template,
                properties=[PropDef(slug="titre", label="Titre", type="text")],
            )
        ],
    )


async def _db_content_template(pool: asyncpg.Pool, ws_slug: str) -> str | None:
    return await pool.fetchval(  # type: ignore[no-any-return]
        "SELECT ft.content_template FROM functional_type ft"
        " JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key"
        " WHERE w.slug = $1 AND ft.slug = 'epic'",
        ws_slug,
    )


@pytest.fixture()
async def ws(db_pool: asyncpg.Pool, request: pytest.FixtureRequest) -> Any:
    slug = f"ct-{abs(hash(request.node.name)) % 10**8}"
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug=slug, label="CT"), None)
    yield slug
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", slug)


# ── Résolution d'héritage ───────────────────────────────────────────────────


def test_resolve_propagates_content_template() -> None:
    resolved = resolve(_tpl(1, content_template=_BODY))
    assert resolved[0].content_template == _BODY


def test_resolve_inherits_content_template_from_parent() -> None:
    """Un type qui hérite sans redéfinir `content_template` reprend celui de son
    ancêtre — même règle que les propriétés."""
    tpl = Template(
        version=1,
        template=_TEMPLATE_SLUG,
        label="CT Test",
        functional_types=[
            TypeDef(slug="base", abstract=True, content_template=_BODY),
            TypeDef(slug="child", inherit="base"),
        ],
    )
    child = next(r for r in resolve(tpl) if r.slug == "child")
    assert child.content_template == _BODY


def test_resolve_override_content_template_wins() -> None:
    tpl = Template(
        version=1,
        template=_TEMPLATE_SLUG,
        label="CT Test",
        functional_types=[
            TypeDef(slug="base", abstract=True, content_template=_BODY),
            TypeDef(slug="child", inherit="base", content_template="# Autre"),
        ],
    )
    child = next(r for r in resolve(tpl) if r.slug == "child")
    assert child.content_template == "# Autre"


def test_resolve_without_content_template_is_none() -> None:
    resolved = resolve(_tpl(1, content_template=None))
    assert resolved[0].content_template is None


# ── Import ──────────────────────────────────────────────────────────────────


async def test_import_writes_content_template(db_pool: asyncpg.Pool, ws: str) -> None:
    report = await run_import(db_pool, ws, _tpl(1, content_template=_BODY))
    assert report.applied
    assert await _db_content_template(db_pool, ws) == _BODY


async def test_reimport_updates_content_template(db_pool: asyncpg.Pool, ws: str) -> None:
    await run_import(db_pool, ws, _tpl(1, content_template=_BODY))

    report = await run_import(db_pool, ws, _tpl(2, content_template="# Nouveau\n"))
    assert report.applied
    assert [i.path for i in report.diff.soft_updates] == ["epic"]
    assert await _db_content_template(db_pool, ws) == "# Nouveau\n"


async def test_unchanged_content_template_is_no_op(db_pool: asyncpg.Pool, ws: str) -> None:
    await run_import(db_pool, ws, _tpl(1, content_template=_BODY))
    report = await run_import(db_pool, ws, _tpl(1, content_template=_BODY))
    assert report.no_op


async def test_absent_content_template_preserves_existing(db_pool: asyncpg.Pool, ws: str) -> None:
    """Réconciliation additive : un template muet sur `content_template` ne doit
    pas effacer celui posé en base (édition manuelle, ou version antérieure)."""
    await run_import(db_pool, ws, _tpl(1, content_template=_BODY))

    report = await run_import(db_pool, ws, _tpl(2, content_template=None, label="Épopée"))
    assert report.applied
    assert [i.path for i in report.diff.soft_updates] == ["epic"]
    assert await _db_content_template(db_pool, ws) == _BODY

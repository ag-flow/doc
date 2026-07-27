"""Provenance des types fonctionnels (source_template, migration 0038).

Un type créé par import de template porte le slug du template ; un type créé
manuellement reste sans provenance ; un ré-import réconcilie les types
antérieurs à la colonne (provenance NULL) même quand l'import est no_op.
"""

from __future__ import annotations

import asyncpg
import pytest

from docflow.schemas.types import FunctionalTypeCreate
from docflow.schemas.workspace import WorkspaceCreate
from docflow.templates.importer import run_import
from docflow.templates.models import Template, TypeDef
from docflow.types import service as types_svc
from docflow.workspaces import service as ws_svc

_TPL = Template(
    version=1,
    template="mini-agile",
    label="Mini agile",
    functional_types=[
        TypeDef(slug="epic", label="Epic"),
        TypeDef(slug="feature", label="Feature", parent="epic"),
    ],
)


@pytest.fixture
async def ws(db_pool: asyncpg.Pool):
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="prov-test", label="Prov"), None)
    yield "prov-test"
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "prov-test")


async def _provenances(db_pool: asyncpg.Pool, ws_slug: str) -> dict[str, str | None]:
    rows = await db_pool.fetch(
        """
        SELECT ft.slug, ft.source_template FROM functional_type ft
        JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key
        WHERE w.slug = $1
        """,
        ws_slug,
    )
    return {r["slug"]: r["source_template"] for r in rows}


async def test_import_stamps_source_template(db_pool: asyncpg.Pool, ws: str) -> None:
    report = await run_import(db_pool, ws, _TPL)
    assert report.applied
    assert await _provenances(db_pool, ws) == {"epic": "mini-agile", "feature": "mini-agile"}


async def test_manual_type_has_no_source_template(db_pool: asyncpg.Pool, ws: str) -> None:
    await types_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="manuel", label="Manuel"))
    assert (await _provenances(db_pool, ws))["manuel"] is None
    # Et l'API l'expose
    out = await types_svc.get_type(db_pool, ws, "manuel")
    assert out.source_template is None


async def test_reimport_no_op_backfills_null_provenance(db_pool: asyncpg.Pool, ws: str) -> None:
    """Données d'avant la colonne : provenance NULL → réconciliée au ré-import no_op."""
    await run_import(db_pool, ws, _TPL)
    await db_pool.execute(
        """
        UPDATE functional_type SET source_template = NULL
        WHERE workspace_technical_key =
            (SELECT workspace_technical_key FROM workspace WHERE slug = $1)
        """,
        ws,
    )
    report = await run_import(db_pool, ws, _TPL)
    assert report.no_op
    assert await _provenances(db_pool, ws) == {"epic": "mini-agile", "feature": "mini-agile"}


async def test_rich_endpoint_exposes_source_template(db_pool: asyncpg.Pool, ws: str) -> None:
    await run_import(db_pool, ws, _TPL)
    rich = await types_svc.list_types_rich(db_pool, ws)
    assert {t.slug: t.source_template for t in rich} == {
        "epic": "mini-agile",
        "feature": "mini-agile",
    }

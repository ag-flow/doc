from __future__ import annotations

import pathlib

import asyncpg
import pytest
import yaml

from docflow.schemas.workspace import WorkspaceCreate
from docflow.templates.importer import (
    ImportConflictError,
    VersionConflictError,
    run_import,
)
from docflow.templates.inheritance import InheritanceCycleError, resolve
from docflow.templates.models import (
    AllowedValueDef,
    ConstraintDef,
    PropDef,
    Template,
    TypeDef,
)
from docflow.workspaces import service as ws_svc

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent.parent / "templates"


def _load(path: pathlib.Path) -> Template:
    with path.open() as f:
        return Template.model_validate(yaml.safe_load(f))


# ── Modèles pydantic ─────────────────────────────────────────────────────────

def test_template_model_extra_field_rejected() -> None:
    with pytest.raises(Exception):
        Template.model_validate({
            "version": 1,
            "template": "t",
            "label": "T",
            "functional_types": [],
            "unexpected": True,
        })


def test_prop_def_type_enum() -> None:
    with pytest.raises(Exception):
        PropDef(slug="p", label="P", type="boolean")  # type: ignore[arg-type]


# ── Résolution d'héritage ────────────────────────────────────────────────────

def test_resolve_excludes_abstract() -> None:
    tpl = Template(
        version=1, template="t", label="T",
        functional_types=[
            TypeDef(slug="base", abstract=True, properties=[PropDef(slug="p", label="P", type="text")]),
            TypeDef(slug="concrete", inherit="base"),
        ],
    )
    resolved = resolve(tpl)
    assert len(resolved) == 1
    assert resolved[0].slug == "concrete"
    assert any(p.slug == "p" for p in resolved[0].properties)


def test_resolve_override_by_slug() -> None:
    tpl = Template(
        version=1, template="t", label="T",
        functional_types=[
            TypeDef(slug="base", abstract=True, properties=[
                PropDef(slug="statut", label="Statut base", type="restricted_list"),
            ]),
            TypeDef(slug="child", inherit="base", properties=[
                PropDef(slug="statut", label="Statut custom", type="restricted_list"),
            ]),
        ],
    )
    resolved = resolve(tpl)
    child = next(r for r in resolved if r.slug == "child")
    statut = next(p for p in child.properties if p.slug == "statut")
    assert statut.label == "Statut custom"


def test_resolve_cycle_detected() -> None:
    tpl = Template(
        version=1, template="t", label="T",
        functional_types=[
            TypeDef(slug="a", inherit="b"),
            TypeDef(slug="b", inherit="a"),
        ],
    )
    with pytest.raises(InheritanceCycleError):
        resolve(tpl)


def test_resolve_unknown_inherit_raises() -> None:
    tpl = Template(
        version=1, template="t", label="T",
        functional_types=[TypeDef(slug="a", inherit="ghost")],
    )
    with pytest.raises(ValueError, match="ghost"):
        resolve(tpl)


def test_agile_basic_has_5_concrete_types() -> None:
    tpl = _load(TEMPLATES_DIR / "agile-basic.yaml")
    resolved = resolve(tpl)
    slugs = {r.slug for r in resolved}
    assert "base_statusable" not in slugs
    assert len(slugs) == 5
    assert {"epic", "feature", "story", "atdd", "task"} == slugs


def test_agile_basic_story_atdd_parent_is_feature() -> None:
    tpl = _load(TEMPLATES_DIR / "agile-basic.yaml")
    by_slug = {td.slug: td for td in tpl.functional_types}
    assert by_slug["story"].parent == "feature"
    assert by_slug["atdd"].parent == "feature"


def test_agile_basic_epic_feature_statut_overridden() -> None:
    tpl = _load(TEMPLATES_DIR / "agile-basic.yaml")
    resolved = resolve(tpl)
    by_slug = {r.slug: r for r in resolved}

    # epic et feature ont un statut différent de la base (default overridé)
    epic_statut = next(p for p in by_slug["epic"].properties if p.slug == "statut")
    assert epic_statut.default != "a_faire"  # base default est a_faire

    # story et atdd héritent le statut de base sans override
    story_statut = next(p for p in by_slug["story"].properties if p.slug == "statut")
    assert story_statut.default == "a_faire"


# ── Import (nécessite DB) ────────────────────────────────────────────────────

async def test_import_fresh_workspace(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-test", label="Tpl Test"))
    try:
        tpl = _load(TEMPLATES_DIR / "agile-basic.yaml")
        report = await run_import(db_pool, "tpl-test", tpl)
        assert report.applied
        assert not report.no_op

        # Vérifie les 5 types en base
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ft.slug FROM functional_type ft
                JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key
                WHERE w.slug = $1
                """,
                "tpl-test",
            )
        slugs = {r["slug"] for r in rows}
        assert {"epic", "feature", "story", "atdd", "task"} == slugs
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-test")


async def test_import_same_version_noop(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-noop", label="Tpl Noop"))
    try:
        tpl = _load(TEMPLATES_DIR / "agile-basic.yaml")
        await run_import(db_pool, "tpl-noop", tpl)

        async with db_pool.acquire() as conn:
            before = await conn.fetchval(
                """
                SELECT wi.imported_at FROM workspace_template_import wi
                JOIN workspace w ON w.workspace_technical_key = wi.workspace_technical_key
                WHERE w.slug = $1 AND wi.template = $2
                """,
                "tpl-noop", tpl.template,
            )

        report2 = await run_import(db_pool, "tpl-noop", tpl)
        assert report2.no_op

        async with db_pool.acquire() as conn:
            after = await conn.fetchval(
                """
                SELECT wi.imported_at FROM workspace_template_import wi
                JOIN workspace w ON w.workspace_technical_key = wi.workspace_technical_key
                WHERE w.slug = $1 AND wi.template = $2
                """,
                "tpl-noop", tpl.template,
            )
        assert before == after  # imported_at inchangé
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-noop")


async def test_import_version_upgrade_additive(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-upgrade", label="Upgrade"))
    try:
        tpl_v1 = _load(TEMPLATES_DIR / "agile-basic.yaml")
        await run_import(db_pool, "tpl-upgrade", tpl_v1)

        # v2 : ajoute une propriété sur 'epic'
        raw = yaml.safe_load((TEMPLATES_DIR / "agile-basic.yaml").read_text())
        raw["version"] = 2
        for td in raw["functional_types"]:
            if td["slug"] == "epic":
                td.setdefault("properties", []).append({
                    "slug": "sponsor",
                    "label": "Sponsor",
                    "type": "text",
                })
        tpl_v2 = Template.model_validate(raw)
        report = await run_import(db_pool, "tpl-upgrade", tpl_v2)
        assert report.applied

        async with db_pool.acquire() as conn:
            version = await conn.fetchval(
                """
                SELECT wi.version FROM workspace_template_import wi
                JOIN workspace w ON w.workspace_technical_key = wi.workspace_technical_key
                WHERE w.slug = $1 AND wi.template = $2
                """,
                "tpl-upgrade", tpl_v2.template,
            )
        assert version == 2
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-upgrade")


async def test_import_version_downgrade_rejected(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-down", label="Down"))
    try:
        tpl = _load(TEMPLATES_DIR / "agile-basic.yaml")
        await run_import(db_pool, "tpl-down", tpl)

        raw = yaml.safe_load((TEMPLATES_DIR / "agile-basic.yaml").read_text())
        raw["version"] = 0
        tpl_v0 = Template.model_validate(raw)
        with pytest.raises(VersionConflictError):
            await run_import(db_pool, "tpl-down", tpl_v0)
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-down")


async def test_import_conflict_blocks_all_writes(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-conflict", label="Conflict"))
    try:
        tpl_v1 = _load(TEMPLATES_DIR / "agile-basic.yaml")
        await run_import(db_pool, "tpl-conflict", tpl_v1)

        # v2 : change le TYPE d'une propriété (conflit structurel)
        raw = yaml.safe_load((TEMPLATES_DIR / "agile-basic.yaml").read_text())
        raw["version"] = 2
        for td in raw["functional_types"]:
            if td["slug"] == "story":
                for p in td.get("properties", []):
                    if p["slug"] == "points":
                        p["type"] = "text"  # text au lieu de int => conflit
        tpl_v2 = Template.model_validate(raw)

        with pytest.raises(ImportConflictError):
            await run_import(db_pool, "tpl-conflict", tpl_v2)

        # La base est STRICTEMENT inchangée — version toujours 1
        async with db_pool.acquire() as conn:
            version = await conn.fetchval(
                """
                SELECT wi.version FROM workspace_template_import wi
                JOIN workspace w ON w.workspace_technical_key = wi.workspace_technical_key
                WHERE w.slug = $1 AND wi.template = $2
                """,
                "tpl-conflict", tpl_v1.template,
            )
        assert version == 1
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-conflict")


async def test_import_dry_run_no_write(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-dry", label="Dry"))
    try:
        tpl = _load(TEMPLATES_DIR / "agile-basic.yaml")
        report = await run_import(db_pool, "tpl-dry", tpl, dry_run=True)
        assert report.dry_run
        assert not report.applied

        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT count(*) FROM functional_type ft
                JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key
                WHERE w.slug = $1
                """,
                "tpl-dry",
            )
        assert count == 0  # rien écrit
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-dry")

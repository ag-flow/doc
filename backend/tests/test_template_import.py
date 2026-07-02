from __future__ import annotations

import pathlib

import asyncpg
import pytest
import yaml

from docflow.schemas.workspace import WorkspaceCreate
from docflow.templates.importer import (
    ImportConflictError,
    UnresolvedTargetTypeError,
    VersionConflictError,
    run_import,
)
from docflow.templates.inheritance import InheritanceCycleError, resolve
from docflow.templates.models import (
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
    with pytest.raises(ValueError):
        Template.model_validate({
            "version": 1,
            "template": "t",
            "label": "T",
            "functional_types": [],
            "unexpected": True,
        })


def test_prop_def_type_enum() -> None:
    with pytest.raises(ValueError):
        PropDef(slug="p", label="P", type="boolean")  # type: ignore[arg-type]


def test_prop_def_type_accepts_url_and_float() -> None:
    """Régression : le CHECK SQL (0025) et le moteur de valeurs acceptent url/float,
    le modèle d'import doit les accepter aussi."""
    PropDef(slug="p1", label="P1", type="url")
    PropDef(slug="p2", label="P2", type="float")


# ── Résolution d'héritage ────────────────────────────────────────────────────

def test_resolve_excludes_abstract() -> None:
    tpl = Template(
        version=1, template="t", label="T",
        functional_types=[
            TypeDef(
                slug="base", abstract=True,
                properties=[PropDef(slug="p", label="P", type="text")],
            ),
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


def test_agile_basic_has_7_concrete_types() -> None:
    tpl = _load(TEMPLATES_DIR / "agile-basic.yaml")
    resolved = resolve(tpl)
    slugs = {r.slug for r in resolved}
    assert "base_statusable" not in slugs
    assert len(slugs) == 7
    assert {"personne", "epic", "feature", "story", "atdd", "bug", "enabler"} == slugs


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
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-test", label="Tpl Test"), None)
    try:
        tpl = _load(TEMPLATES_DIR / "agile-basic.yaml")
        report = await run_import(db_pool, "tpl-test", tpl)
        assert report.applied
        assert not report.no_op

        # Vérifie les 7 types concrets en base
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
        assert {"personne", "epic", "feature", "story", "atdd", "bug", "enabler"} == slugs
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-test")


async def test_import_allowed_values_populated(db_pool: asyncpg.Pool) -> None:
    """Régression : les allowed_values d'une prop restricted_list doivent être insérées."""
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-av", label="AV Test"), None)
    try:
        tpl = _load(TEMPLATES_DIR / "agile-basic.yaml")
        await run_import(db_pool, "tpl-av", tpl)

        async with db_pool.acquire() as conn:
            # epic.statut doit avoir 4 allowed_values (a_cadrer, cadre, en_cours, done)
            count = await conn.fetchval(
                """
                SELECT count(*) FROM properties_allowed_values av
                JOIN properties_defs pd ON pd.id = av.property_def_ref
                JOIN functional_type ft ON ft.id = pd.functional_type_ref
                JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key
                WHERE w.slug = $1 AND ft.slug = 'epic' AND pd.slug = 'statut'
                """,
                "tpl-av",
            )
        assert count == 4, f"epic.statut devrait avoir 4 allowed_values, got {count}"

        async with db_pool.acquire() as conn:
            # story.statut hérite de base_statusable : 4 valeurs (a_faire, en_cours, en_review, done)
            count = await conn.fetchval(
                """
                SELECT count(*) FROM properties_allowed_values av
                JOIN properties_defs pd ON pd.id = av.property_def_ref
                JOIN functional_type ft ON ft.id = pd.functional_type_ref
                JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key
                WHERE w.slug = $1 AND ft.slug = 'story' AND pd.slug = 'statut'
                """,
                "tpl-av",
            )
        assert count == 4, f"story.statut devrait avoir 4 allowed_values, got {count}"
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-av")


async def test_import_same_version_noop(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-noop", label="Tpl Noop"), None)
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
    await ws_svc.create_workspace(
        db_pool, WorkspaceCreate(slug="tpl-upgrade", label="Upgrade"), None
    )
    try:
        tpl_v1 = _load(TEMPLATES_DIR / "agile-basic.yaml")
        await run_import(db_pool, "tpl-upgrade", tpl_v1)

        # v2 : ajoute une propriété sur 'epic'
        raw = yaml.safe_load((TEMPLATES_DIR / "agile-basic.yaml").read_text())
        raw["version"] = tpl_v1.version + 1
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
        assert version == tpl_v1.version + 1
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-upgrade")


async def test_import_version_downgrade_rejected(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-down", label="Down"), None)
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
    await ws_svc.create_workspace(
        db_pool, WorkspaceCreate(slug="tpl-conflict", label="Conflict"), None
    )
    try:
        tpl_v1 = _load(TEMPLATES_DIR / "agile-basic.yaml")
        await run_import(db_pool, "tpl-conflict", tpl_v1)

        # v2 : change le TYPE d'une propriété (conflit structurel)
        raw = yaml.safe_load((TEMPLATES_DIR / "agile-basic.yaml").read_text())
        raw["version"] = tpl_v1.version + 1
        for td in raw["functional_types"]:
            if td["slug"] == "story":
                for p in td.get("properties", []):
                    if p["slug"] == "points":
                        p["type"] = "text"  # text au lieu de int => conflit
        tpl_v2 = Template.model_validate(raw)

        with pytest.raises(ImportConflictError):
            await run_import(db_pool, "tpl-conflict", tpl_v2)

        # La base est STRICTEMENT inchangée — version toujours celle de tpl_v1
        async with db_pool.acquire() as conn:
            version = await conn.fetchval(
                """
                SELECT wi.version FROM workspace_template_import wi
                JOIN workspace w ON w.workspace_technical_key = wi.workspace_technical_key
                WHERE w.slug = $1 AND wi.template = $2
                """,
                "tpl-conflict", tpl_v1.template,
            )
        assert version == tpl_v1.version
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-conflict")


async def test_import_dry_run_no_write(db_pool: asyncpg.Pool) -> None:
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-dry", label="Dry"), None)
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


# ── target_type → target_functional_type_ref (MREL) ─────────────────────────


def _reference_template(version: int, target_type: str | None) -> Template:
    return Template(
        version=version,
        template="ref-test",
        label="Ref Test",
        functional_types=[
            TypeDef(slug="personne", label="Personne"),
            TypeDef(
                slug="feature",
                label="Feature",
                properties=[
                    PropDef(
                        slug="assignee",
                        label="Assigné à",
                        type="reference",
                        target_type=target_type,
                    ),
                ],
            ),
        ],
    )


async def test_import_reference_target_type_written(db_pool: asyncpg.Pool) -> None:
    """target_type='personne' doit résoudre vers l'id du type 'personne' importé
    dans le même template, écrit dans properties_defs.target_functional_type_ref."""
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-ref", label="Ref"), None)
    try:
        tpl = _reference_template(version=1, target_type="personne")
        report = await run_import(db_pool, "tpl-ref", tpl)
        assert report.applied

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT target.slug AS target_slug
                FROM properties_defs pd
                JOIN functional_type ft ON ft.id = pd.functional_type_ref
                JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key
                JOIN functional_type target ON target.id = pd.target_functional_type_ref
                WHERE w.slug = $1 AND ft.slug = 'feature' AND pd.slug = 'assignee'
                """,
                "tpl-ref",
            )
        assert row is not None
        assert row["target_slug"] == "personne"
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-ref")


async def test_import_unresolved_target_type_raises(db_pool: asyncpg.Pool) -> None:
    """target_type pointant vers un slug introuvable (ni workspace, ni template) : rejet
    explicite avant toute écriture — jamais un target_functional_type_ref NULL silencieux."""
    await ws_svc.create_workspace(
        db_pool, WorkspaceCreate(slug="tpl-ref-bad", label="Ref Bad"), None
    )
    try:
        tpl = _reference_template(version=1, target_type="ghost")
        with pytest.raises(UnresolvedTargetTypeError, match="ghost"):
            await run_import(db_pool, "tpl-ref-bad", tpl)

        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT count(*) FROM functional_type ft
                JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key
                WHERE w.slug = $1
                """,
                "tpl-ref-bad",
            )
        assert count == 0  # rien écrit
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-ref-bad")


async def test_import_target_type_change_conflicts(db_pool: asyncpg.Pool) -> None:
    """Changer le target_type d'une propriété reference déjà publiée est un conflit
    structurel (comme un changement de `type`) : import bloqué en entier."""
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug="tpl-ref-chg", label="Chg"), None)
    try:
        tpl_v1 = _reference_template(version=1, target_type="personne")
        await run_import(db_pool, "tpl-ref-chg", tpl_v1)

        tpl_v2 = Template(
            version=2,
            template="ref-test",
            label="Ref Test",
            functional_types=[
                TypeDef(slug="personne", label="Personne"),
                TypeDef(slug="autre_cible", label="Autre cible"),
                TypeDef(
                    slug="feature",
                    label="Feature",
                    properties=[
                        PropDef(
                            slug="assignee",
                            label="Assigné à",
                            type="reference",
                            target_type="autre_cible",
                        ),
                    ],
                ),
            ],
        )
        with pytest.raises(ImportConflictError):
            await run_import(db_pool, "tpl-ref-chg", tpl_v2)

        async with db_pool.acquire() as conn:
            version = await conn.fetchval(
                """
                SELECT wi.version FROM workspace_template_import wi
                JOIN workspace w ON w.workspace_technical_key = wi.workspace_technical_key
                WHERE w.slug = $1 AND wi.template = $2
                """,
                "tpl-ref-chg", "ref-test",
            )
        assert version == 1  # inchangé
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", "tpl-ref-chg")

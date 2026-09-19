"""Template global `modele-de-donnees` (épic MLD — F8)."""

from __future__ import annotations

import asyncpg
import pytest

from docflow.templates.catalog import find_template

SLUG = "modele-de-donnees"


@pytest.fixture()
def template():
    return find_template(SLUG)


# ── Le catalogue le trouve ────────────────────────────────────────────────────


def test_le_template_est_decouvert_par_le_catalogue(template) -> None:
    assert template.template == SLUG
    assert template.label == "Modèle de données"


# ── Vocabulaire imposé par le cadrage ────────────────────────────────────────


def test_les_types_sont_modele_et_entite(template) -> None:
    """`entite`, pas `table` : on décrit un modèle LOGIQUE, pas un schéma physique.

    Et on évite `context`, déjà pris par le vocabulaire des workflows — deux
    sens sous un même mot rendraient les deux illisibles.
    """
    slugs = {t.slug for t in template.functional_types}

    assert slugs == {"modele", "entite"}
    assert "table" not in slugs
    assert "context" not in slugs


def test_l_entite_est_enfant_du_modele(template) -> None:
    """L'appartenance au modèle est l'arborescence : la hiérarchie de types la porte."""
    entite = next(t for t in template.functional_types if t.slug == "entite")
    assert entite.parent == "modele"


# ── Propriétés ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("type_slug", ["modele", "entite"])
def test_chaque_type_porte_un_statut_obligatoire(template, type_slug: str) -> None:
    statut = next(
        p
        for t in template.functional_types
        if t.slug == type_slug
        for p in t.properties
        if p.slug == "statut"
    )
    assert statut.required is True
    assert statut.type == "restricted_list"
    assert statut.default == "brouillon"
    # Les valeurs sont ordonnées : le rang fait le pipeline.
    positions = [v.position for v in statut.allowed_values]
    assert positions == sorted(positions)


def test_l_entite_distingue_la_nature_des_tables(template) -> None:
    entite = next(t for t in template.functional_types if t.slug == "entite")
    nature = next(p for p in entite.properties if p.slug == "nature")
    assert {v.slug for v in nature.allowed_values} == {
        "principale",
        "reference",
        "association",
        "technique",
    }


def test_la_volumetrie_ne_peut_pas_etre_negative(template) -> None:
    entite = next(t for t in template.functional_types if t.slug == "entite")
    volumetrie = next(p for p in entite.properties if p.slug == "volumetrie_estimee")
    assert volumetrie.type == "int"
    assert any(c.kind == "min" and c.value == "0" for c in volumetrie.constraints)


def test_la_date_de_mise_a_jour_est_automatique(template) -> None:
    for type_slug in ("modele", "entite"):
        prop = next(
            p
            for t in template.functional_types
            if t.slug == type_slug
            for p in t.properties
            if p.slug == "mis_a_jour_le"
        )
        assert prop.type == "date"
        assert prop.behavior == "auto_now"


# ── Import de bout en bout ────────────────────────────────────────────────────


async def test_le_template_s_importe_dans_un_workspace(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    """Le vrai test : importable tel quel, et les types atterrissent en base."""
    from docflow.templates.importer import run_import

    await run_import(db_pool, "test-ws", find_template(SLUG))

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ft.slug, parent.slug AS parent_slug "
            "FROM functional_type ft "
            "LEFT JOIN functional_type parent ON parent.id = ft.parent "
            "WHERE ft.workspace_technical_key = $1",
            test_workspace["workspace_technical_key"],
        )

    by_slug = {r["slug"]: r["parent_slug"] for r in rows}
    assert "modele" in by_slug
    assert by_slug["entite"] == "modele"


async def test_l_import_est_idempotent(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    """Réimporter ne doit pas dupliquer les types."""
    from docflow.templates.importer import run_import

    await run_import(db_pool, "test-ws", find_template(SLUG))
    await run_import(db_pool, "test-ws", find_template(SLUG))

    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM functional_type "
            "WHERE workspace_technical_key = $1 AND slug = ANY($2::text[])",
            test_workspace["workspace_technical_key"],
            ["modele", "entite"],
        )
    assert count == 2

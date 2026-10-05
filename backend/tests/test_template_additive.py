"""Garde-fou de la mise à jour d'un workspace depuis un template global :
la réconciliation est **strictement additive**. Une version qui retire un type
ou une propriété ne les supprime JAMAIS du workspace — sinon documents et valeurs
deviendraient orphelins. Invariant verrouillé ici (indépendant du dossier
templates/ : templates construits en mémoire).
"""

from __future__ import annotations

import asyncpg

from docflow.templates.importer import run_import
from docflow.templates.models import PropDef, Template, TypeDef


def _tpl(version: int, types: list[TypeDef]) -> Template:
    return Template(version=version, template="additive-test", label="T", functional_types=types)


async def test_update_is_strictly_additive_no_deletion(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    wk = await db_pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = 'test-ws'"
    )

    # v1 : alpha(keep, dropme) + beta(x)
    v1 = _tpl(
        1,
        [
            TypeDef(
                slug="alpha",
                label="Alpha",
                properties=[
                    PropDef(slug="keep", label="K", type="text"),
                    PropDef(slug="dropme", label="D", type="text"),
                ],
            ),
            TypeDef(
                slug="beta", label="Beta", properties=[PropDef(slug="x", label="X", type="text")]
            ),
        ],
    )
    r1 = await run_import(db_pool, "test-ws", v1)
    assert not r1.no_op

    # Un document de type `beta` (le type que v2 "retire") + un document `alpha` :
    # ils ne doivent jamais devenir orphelins.
    ft_beta = await db_pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'beta'", wk
    )
    blk_beta = await db_pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ('beta-blk', 'Beta', $1, $2) RETURNING id",
        ft_beta,
        wk,
    )
    doc_beta = await db_pool.fetchval(
        "INSERT INTO document "
        "(title, functional_type_ref, data_block_ref, workspace_technical_key) "
        "VALUES ('doc beta', $1, $2, $3) RETURNING doc_technical_key",
        ft_beta,
        blk_beta,
        wk,
    )

    # v2 : alpha perd `dropme` et gagne `added` ; `beta` disparaît du template.
    v2 = _tpl(
        2,
        [
            TypeDef(
                slug="alpha",
                label="Alpha",
                properties=[
                    PropDef(slug="keep", label="K", type="text"),
                    PropDef(slug="added", label="A", type="text"),
                ],
            ),
        ],
    )
    report = await run_import(db_pool, "test-ws", v2)
    assert not report.no_op

    # Le type absent de la nouvelle version n'est JAMAIS supprimé.
    types = {
        r["slug"]
        for r in await db_pool.fetch(
            "SELECT slug FROM functional_type WHERE workspace_technical_key = $1", wk
        )
    }
    assert "beta" in types
    assert "alpha" in types

    # La propriété absente de la nouvelle version n'est JAMAIS supprimée ; l'ajout l'est.
    props = {
        r["slug"]
        for r in await db_pool.fetch(
            "SELECT pd.slug FROM properties_defs pd "
            "JOIN functional_type ft ON ft.id = pd.functional_type_ref "
            "WHERE ft.workspace_technical_key = $1 AND ft.slug = 'alpha'",
            wk,
        )
    }
    assert "dropme" in props  # retiré du template → conservé
    assert "keep" in props
    assert "added" in props  # ajout appliqué (additif)

    # Le document de type `beta` survit — aucun orphelin.
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM document WHERE doc_technical_key = $1", doc_beta
        )
        == 1
    )

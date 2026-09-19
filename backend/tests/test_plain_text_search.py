"""Matérialisation de `plain_text` et recherche par le sens (épic MLD — F3b)."""

from __future__ import annotations

import asyncpg
import pytest

from docflow.codecs import codec_for
from docflow.db.backfill_plain_text import backfill
from docflow.documents import service as doc_svc
from docflow.references.service import search_documents_global
from docflow.schemas.document import DocumentCreate, DocumentUpdate

MARKDOWN = "# Titre\n\nVoir [la documentation](https://exemple.test/page) pour **cadrer**.\n"


async def _create(db_pool: asyncpg.Pool, block: dict[str, object], title: str, content: str):
    return await doc_svc.create_document(
        db_pool,
        "test-ws",
        DocumentCreate(
            title=title,
            block_id=block["id"],  # type: ignore[arg-type]
            content=content,
        ),
    )


async def _plain_text_of(db_pool: asyncpg.Pool, doc_id, version: int) -> str | None:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT plain_text FROM document_version "
            "WHERE document_ref = $1 AND version_number = $2",
            doc_id,
            version,
        )


# ── Écriture au save ──────────────────────────────────────────────────────────


async def test_projection_ecrite_a_la_creation(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    created = await _create(db_pool, test_block, "Doc projeté", MARKDOWN)
    plain = await _plain_text_of(db_pool, created.doc_technical_key, 1)

    assert plain is not None
    # La syntaxe est retirée, le sens est gardé.
    assert "la documentation" in plain
    assert "exemple.test" not in plain
    assert "#" not in plain and "**" not in plain


async def test_projection_ecrite_a_chaque_revision(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    created = await _create(db_pool, test_block, "Doc versionné", "# Un\n")
    await doc_svc.update_document(
        db_pool,
        "test-ws",
        created.doc_technical_key,
        DocumentUpdate(content="# Deux **gras**\n", expected_version=created.version),
    )
    plain = await _plain_text_of(db_pool, created.doc_technical_key, created.version + 1)

    assert plain is not None
    assert "Deux" in plain and "gras" in plain
    assert "**" not in plain


# ── Recherche ─────────────────────────────────────────────────────────────────


async def test_recherche_trouve_par_le_libelle_du_lien(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    await _create(db_pool, test_block, "Doc cherchable", MARKDOWN)

    found = await search_documents_global(db_pool, "la documentation", 10, allowed_ws=None)
    assert any(r.title == "Doc cherchable" for r in found)


async def test_recherche_ignore_l_url_qui_n_est_pas_du_sens(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """L'URL d'un lien est de la syntaxe : elle ne doit plus faire matcher."""
    await _create(db_pool, test_block, "Doc avec url", MARKDOWN)

    found = await search_documents_global(db_pool, "exemple.test", 10, allowed_ws=None)
    assert not any(r.title == "Doc avec url" for r in found)


async def test_recherche_retombe_sur_le_contenu_brut_si_non_repris(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Révision écrite AVANT la migration : plain_text NULL.

    C'est le cas d'une base existante au moment du déploiement. La recherche
    doit continuer de fonctionner exactement comme avant — sans quoi la
    migration ouvrirait un trou de recherche jusqu'au passage du backfill.
    """
    created = await _create(db_pool, test_block, "Doc ancien", "Contenu historique singulier.")
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE document_version SET plain_text = NULL WHERE document_ref = $1",
            created.doc_technical_key,
        )

    found = await search_documents_global(db_pool, "historique singulier", 10, allowed_ws=None)
    assert any(r.title == "Doc ancien" for r in found)


# ── Backfill ──────────────────────────────────────────────────────────────────


async def test_backfill_reprend_les_revisions_sans_projection(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    created = await _create(db_pool, test_block, "Doc à reprendre", MARKDOWN)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE document_version SET plain_text = NULL WHERE document_ref = $1",
            created.doc_technical_key,
        )

    treated = await backfill(db_pool)

    assert treated >= 1
    plain = await _plain_text_of(db_pool, created.doc_technical_key, 1)
    assert plain is not None
    assert "la documentation" in plain
    assert "exemple.test" not in plain


async def test_backfill_est_idempotent(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Rejouer le backfill ne doit rien faire : il ne vise que plain_text IS NULL."""
    created = await _create(db_pool, test_block, "Doc idempotent", MARKDOWN)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE document_version SET plain_text = NULL WHERE document_ref = $1",
            created.doc_technical_key,
        )

    await backfill(db_pool)
    before = await _plain_text_of(db_pool, created.doc_technical_key, 1)

    second = await backfill(db_pool)

    assert second == 0
    assert await _plain_text_of(db_pool, created.doc_technical_key, 1) == before


async def test_backfill_traite_plusieurs_lots(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """La boucle de lots doit tout reprendre, pas seulement le premier lot."""
    for i in range(5):
        created = await _create(db_pool, test_block, f"Doc lot {i}", f"# Titre {i}\n")
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE document_version SET plain_text = NULL WHERE document_ref = $1",
                created.doc_technical_key,
            )

    treated = await backfill(db_pool, batch_size=2)

    assert treated >= 5
    async with db_pool.acquire() as conn:
        remaining = await conn.fetchval(
            "SELECT count(*) FROM document_version WHERE plain_text IS NULL"
        )
    assert remaining == 0


# ── Repli sur type de contenu inconnu ────────────────────────────────────────


@pytest.mark.parametrize("unknown", ["table-schema", "model-layout"])
async def test_type_inconnu_projette_le_contenu_tel_quel(
    db_pool: asyncpg.Pool,
    test_workspace: dict[str, object],
    test_block: dict[str, object],
    unknown: str,
) -> None:
    """Un type sans codec ne doit pas devenir incherchable : repli = contenu brut."""
    brut = "fields:\n  - name: date_naissance\n"
    created = await _create(db_pool, test_block, f"Doc {unknown}", brut)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE document SET type = $2 WHERE doc_technical_key = $1",
            created.doc_technical_key,
            unknown,
        )
        await conn.execute(
            "UPDATE document_version SET plain_text = NULL WHERE document_ref = $1",
            created.doc_technical_key,
        )

    await backfill(db_pool)

    assert await _plain_text_of(db_pool, created.doc_technical_key, 1) == brut
    assert codec_for(unknown).to_plain_text(brut) == brut

"""Type de contenu positionnable + refus structuré (épic MLD — F9)."""

from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.documents.content_validation import CONTENT_INVALID, CONTENT_UNPARSEABLE
from docflow.schemas.document import DocumentCreate, DocumentUpdate

VALID_SCHEMA = """
name: client
description: Un client de la boutique.
fields:
  - name: id
    type: uuid
"""


async def _create(
    db_pool: asyncpg.Pool,
    block: dict[str, object],
    title: str,
    content: str | None = None,
    content_type: str | None = None,
):
    return await doc_svc.create_document(
        db_pool,
        "test-ws",
        DocumentCreate(
            title=title,
            block_id=block["id"],  # type: ignore[arg-type]
            content=content,
            content_type=content_type,
        ),
    )


async def _stored_type(db_pool: asyncpg.Pool, doc_id) -> str:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT type FROM document WHERE doc_technical_key = $1", doc_id
        )


# ── Le type est positionnable à la création ──────────────────────────────────


async def test_le_type_de_contenu_est_positionnable_a_la_creation(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    doc = await _create(db_pool, test_block, "Client", VALID_SCHEMA, "table-schema")
    assert await _stored_type(db_pool, doc.doc_technical_key) == "table-schema"
    assert doc.type == "table-schema"


async def test_le_defaut_reste_md_si_le_type_est_omis(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Rétro-compatibilité : tout appelant existant continue de créer du markdown."""
    doc = await _create(db_pool, test_block, "Page ordinaire", "# Bonjour")
    assert await _stored_type(db_pool, doc.doc_technical_key) == "md"


async def test_un_type_inconnu_est_accepte_et_retombe_sur_le_repli(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Fail-soft : un type hors registre ne casse pas la création, il ne valide rien."""
    doc = await _create(db_pool, test_block, "Type futur", "n'importe quoi", "model-layout")
    assert await _stored_type(db_pool, doc.doc_technical_key) == "model-layout"


# ── Refus structuré ──────────────────────────────────────────────────────────


async def test_un_contenu_illisible_est_refuse(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    with pytest.raises(HTTPException) as exc:
        await _create(db_pool, test_block, "Cassé", "name: t\n  fields: [oups\n", "table-schema")

    assert exc.value.status_code == 422
    detail = exc.value.detail
    assert detail["code"] == CONTENT_UNPARSEABLE
    assert detail["doc"]


async def test_un_contenu_invalide_remonte_toutes_ses_erreurs(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Un appelant doit pouvoir corriger en une passe, pas une erreur à la fois."""
    mauvais = """
name: t
fields:
  - name: a
    type: varchar(255)
  - name: a
    type: licorne
"""
    with pytest.raises(HTTPException) as exc:
        await _create(db_pool, test_block, "Invalide", mauvais, "table-schema")

    detail = exc.value.detail
    assert detail["code"] == CONTENT_INVALID
    codes = {i["code"] for i in detail["issues"]}
    assert {"physical_type", "duplicate_name", "unknown_type"} <= codes

    # Chaque erreur situe le problème…
    assert all("path" in i for i in detail["issues"])
    # …et un mot inconnu vient avec le vocabulaire accepté.
    physique = next(i for i in detail["issues"] if i["code"] == "physical_type")
    assert "string" in physique["allowed"]
    assert "string" in physique["message"]  # le refus enseigne la règle


async def test_le_refus_a_lieu_avant_toute_ecriture(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Un contenu refusé ne doit laisser aucun document derrière lui."""
    async with db_pool.acquire() as conn:
        avant = await conn.fetchval("SELECT count(*) FROM document")

    with pytest.raises(HTTPException):
        await _create(db_pool, test_block, "Jamais créé", "fields: []", "table-schema")

    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM document") == avant


async def test_le_refus_s_applique_aussi_a_la_mise_a_jour(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    doc = await _create(db_pool, test_block, "Client modifiable", VALID_SCHEMA, "table-schema")

    with pytest.raises(HTTPException) as exc:
        await doc_svc.update_document(
            db_pool,
            "test-ws",
            doc.doc_technical_key,
            DocumentUpdate(
                content="name: t\nfields:\n  - name: a\n    type: int\n",
                expected_version=doc.version,
            ),
        )
    assert exc.value.detail["code"] == CONTENT_INVALID


async def test_le_markdown_n_est_jamais_refuse(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Une grammaire libre n'a rien à refuser — aucune régression pour l'existant."""
    doc = await _create(db_pool, test_block, "Markdown libre", "# Titre\n\n``` pas fermé")
    assert doc.type == "md"


@pytest.mark.parametrize("contenu", ["", None])
async def test_un_markdown_vide_reste_accepte(
    db_pool: asyncpg.Pool,
    test_workspace: dict[str, object],
    test_block: dict[str, object],
    contenu: str | None,
) -> None:
    """Créer une page vide est un geste courant : il ne doit pas devenir une erreur."""
    doc = await _create(db_pool, test_block, f"Vide {contenu!r}", contenu)
    assert doc.type == "md"


# ── Le type n'est PAS modifiable par une écriture ────────────────────────────


def test_update_document_ne_porte_pas_de_type_de_contenu() -> None:
    """Décision d'épic : le type est une caractéristique du document, pas de l'écriture.

    Le changer est une opération à part ; l'exposer dans `update_document`
    inviterait à muter la grammaire par effet de bord d'une sauvegarde.
    """
    assert "content_type" not in DocumentUpdate.model_fields

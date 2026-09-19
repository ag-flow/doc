"""Un document `table-schema` bout en bout (épic MLD — F5).

C'est le premier critère d'acceptation de l'épic : « un document `table-schema`
valide se crée, se version, se recherche et expose ses backlinks comme un
document markdown ».
"""

from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.codecs.table_schema import grammar, ids
from docflow.documents import service as doc_svc
from docflow.references.service import get_backlinks, search_documents_global
from docflow.schemas.document import DocumentCreate, DocumentUpdate

SCHEMA = """
name: commande
title: Commande client
description: Une commande passée par un client identifié.
fields:
  - name: id
    type: uuid
    description: Identifiant technique de la commande.
  - name: montant_ttc
    type: number
    title: Montant toutes taxes comprises
"""


async def _create_schema_doc(
    db_pool: asyncpg.Pool, block: dict[str, object], title: str, content: str
):
    """Crée un document et bascule son type de contenu.

    Le type n'est pas encore positionnable à la création (c'est F9) : on le pose
    directement, puis on réécrit le corps pour que la sauvegarde passe par le
    codec `table-schema`.
    """
    created = await doc_svc.create_document(
        db_pool,
        "test-ws",
        DocumentCreate(title=title, block_id=block["id"], content="provisoire"),  # type: ignore[arg-type]
    )
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE document SET type = 'table-schema' WHERE doc_technical_key = $1",
            created.doc_technical_key,
        )
    return await doc_svc.update_document(
        db_pool,
        "test-ws",
        created.doc_technical_key,
        DocumentUpdate(content=content, expected_version=created.version),
    )


async def _current_content(db_pool: asyncpg.Pool, doc_id) -> str:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT dv.content FROM document_version dv "
            "JOIN document d ON d.doc_technical_key = dv.document_ref "
            "AND dv.version_number = d.version WHERE d.doc_technical_key = $1",
            doc_id,
        )


async def test_le_contenu_est_canonicalise_au_save(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """La canonicalisation est faite par le SERVEUR, pas par l'appelant."""
    doc = await _create_schema_doc(db_pool, test_block, "Commande", SCHEMA)
    stored = await _current_content(db_pool, doc.doc_technical_key)

    # Les identifiants stables ont été alloués à l'enregistrement.
    assert f"{grammar.ID_KEY}: {ids.FIELD_PREFIX}" in stored
    # …et l'ordre des clés est figé.
    assert stored.index("name: commande") < stored.index("fields:")


async def test_les_identifiants_survivent_a_une_nouvelle_revision(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Renommer un champ ne doit pas changer son identité."""
    doc = await _create_schema_doc(db_pool, test_block, "Commande stable", SCHEMA)
    stored = await _current_content(db_pool, doc.doc_technical_key)

    renamed = stored.replace("name: montant_ttc", "name: montant_total")
    await doc_svc.update_document(
        db_pool,
        "test-ws",
        doc.doc_technical_key,
        DocumentUpdate(content=renamed, expected_version=doc.version),
    )

    after = await _current_content(db_pool, doc.doc_technical_key)
    before_ids = {line.strip() for line in stored.splitlines() if grammar.ID_KEY in line}
    after_ids = {line.strip() for line in after.splitlines() if grammar.ID_KEY in line}
    assert before_ids == after_ids


async def test_la_recherche_trouve_par_le_sens_pas_par_la_syntaxe(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """La raison d'être de F3b : un table-schema se cherche sur ce qu'il décrit."""
    await _create_schema_doc(db_pool, test_block, "Commande cherchable", SCHEMA)

    trouve = await search_documents_global(db_pool, "toutes taxes comprises", 10, allowed_ws=None)
    assert any(r.title == "Commande cherchable" for r in trouve)

    # « cardinality », « primaryKey »… sont des mots-clés de grammaire : ils ne
    # doivent PAS faire remonter toutes les tables.
    bruit = await search_documents_global(db_pool, "docflow.relations", 10, allowed_ws=None)
    assert not any(r.title == "Commande cherchable" for r in bruit)


async def test_les_backlinks_fonctionnent_comme_pour_un_markdown(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Deuxième moitié du critère d'acceptation : `references()` est exploité."""
    cible = await doc_svc.create_document(
        db_pool,
        "test-ws",
        DocumentCreate(title="Table cible", block_id=test_block["id"], content="# Cible"),  # type: ignore[arg-type]
    )
    contenu = SCHEMA.replace(
        "description: Une commande passée par un client identifié.",
        f"description: voir docflow://doc/{cible.doc_technical_key}",
    )
    source = await _create_schema_doc(db_pool, test_block, "Commande liante", contenu)

    backlinks = await get_backlinks(db_pool, "test-ws", cible.doc_technical_key)
    assert [b.source_id for b in backlinks] == [source.doc_technical_key]


async def test_un_contenu_illisible_est_refuse_avant_d_atteindre_le_stockage(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Depuis F9, le refus a lieu à la frontière de l'API.

    Le garde « la couche de stockage ne détruit jamais » reste vrai et reste
    testé au niveau du codec (`test_codec_table_schema`) : les deux règles se
    complètent — on refuse en amont, et si jamais un contenu illisible passait,
    il serait conservé plutôt qu'effacé.
    """
    with pytest.raises(HTTPException) as exc:
        await _create_schema_doc(db_pool, test_block, "Commande cassée", "name: t\n  f: [oups\n")

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "content_unparseable"

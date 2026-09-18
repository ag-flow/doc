"""Registre de codecs de type de contenu et codec markdown (épic MLD — F3)."""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from docflow.codecs import FALLBACK, REGISTRY, codec_for, codec_for_document
from docflow.codecs.markdown import MarkdownCodec
from docflow.codecs.plain import PlainTextCodec
from docflow.documents import content_types

# ── Registre (unitaire, sans DB) ──────────────────────────────────────────────


def test_markdown_est_servi_par_son_codec() -> None:
    assert isinstance(codec_for("md"), MarkdownCodec)
    assert codec_for("md") is REGISTRY["md"]


@pytest.mark.parametrize("unknown", ["table-schema", "model-layout", "n-importe-quoi", ""])
def test_type_inconnu_retombe_sur_le_repli(unknown: str) -> None:
    """Exigence : un type inconnu ne casse jamais la page."""
    assert codec_for(unknown) is FALLBACK
    assert isinstance(codec_for(unknown), PlainTextCodec)


def test_type_absent_retombe_sur_le_repli() -> None:
    assert codec_for(None) is FALLBACK


def test_le_defaut_du_schema_est_dans_le_registre() -> None:
    """Le défaut DDL de `document.type` doit toujours avoir un codec."""
    assert content_types.DEFAULT in REGISTRY


# ── Codec markdown : références (parité avec l'existant) ──────────────────────


def test_references_markdown_documents_artefacts_datasets() -> None:
    doc_id = "550e8400-e29b-41d4-a716-446655440000"
    art_id = "11111111-2222-3333-4444-555555555555"
    content = (
        f"Voir [la cible](docflow://doc/{doc_id}).\n\n"
        f"![schéma](/api/workspaces/ws/artifacts/{art_id})\n"
    )
    refs = codec_for("md").references(content)
    assert refs.documents == {doc_id: "la cible"}
    assert refs.artifacts == {art_id}


def test_references_contenu_vide_ou_absent() -> None:
    codec = codec_for("md")
    for empty in (None, ""):
        refs = codec.references(empty)
        assert refs.documents == {} and refs.artifacts == set() and refs.datasets == []


def test_repli_n_extrait_jamais_de_references() -> None:
    """Un contenu opaque ne doit jamais produire de liens devinés."""
    doc_id = "550e8400-e29b-41d4-a716-446655440000"
    refs = FALLBACK.references(f"[x](docflow://doc/{doc_id})")
    assert refs.documents == {} and refs.artifacts == set() and refs.datasets == []


def test_repli_ne_declare_pas_savoir_lire_les_references() -> None:
    """Garde-fou anti-destruction : « illisible » ≠ « aucun lien ».

    La réconciliation supprime les artefacts et datasets devenus orphelins.
    Si le repli se déclarait capable d'extraire, un document au type inconnu
    verrait ses références purgées et ses artefacts détruits au premier save.
    """
    assert FALLBACK.extracts_references is False
    assert codec_for("md").extracts_references is True


# ── Codec markdown : projection texte ────────────────────────────────────────


def test_to_plain_text_retire_la_syntaxe() -> None:
    md = (
        "# Titre\n\n"
        "Un **gras**, un *italique* et du `code`.\n\n"
        "> une citation\n\n"
        "- premier\n- second\n"
    )
    text = codec_for("md").to_plain_text(md)
    assert "#" not in text
    assert "**" not in text and "`" not in text
    for expected in ("Titre", "gras", "italique", "code", "une citation", "premier", "second"):
        assert expected in text


def test_to_plain_text_garde_le_libelle_des_liens_pas_l_url() -> None:
    text = codec_for("md").to_plain_text("Voir [la documentation](https://exemple.test/page).")
    assert "la documentation" in text
    assert "exemple.test" not in text


def test_to_plain_text_garde_le_corps_des_blocs_clotures() -> None:
    """Le corps d'un bloc `df-*` est de la donnée cherchable, pas de la syntaxe."""
    text = codec_for("md").to_plain_text('```df-chart type="pie"\nFait | 60\n```')
    assert "Fait | 60" in text
    assert "```" not in text and "df-chart" not in text


def test_to_plain_text_preserve_les_identifiants_snake_case() -> None:
    """L'underscore d'un identifiant n'est pas un marqueur d'emphase."""
    text = codec_for("md").to_plain_text("La clé workspace_technical_key.")
    assert "workspace_technical_key" in text


def test_to_plain_text_contenu_vide() -> None:
    assert codec_for("md").to_plain_text(None) == ""
    assert codec_for("md").to_plain_text("") == ""


def test_repli_rend_le_contenu_tel_quel() -> None:
    brut = "colonnes:\n  - nom: id\n    type: uuid\n"
    assert FALLBACK.to_plain_text(brut) == brut


# ── Round-trip parse/serialize ────────────────────────────────────────────────


@pytest.mark.parametrize("codec", [MarkdownCodec(), PlainTextCodec()])
def test_round_trip_parse_serialize(codec: MarkdownCodec | PlainTextCodec) -> None:
    content = "# Titre\n\nUn paragraphe.\n"
    assert codec.serialize(codec.parse(content)) == content


# ── Résolution depuis la base ────────────────────────────────────────────────


async def test_codec_for_document_lit_le_type_en_base(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], test_block: dict[str, object]
) -> None:
    """Un document naît au défaut DDL `'md'` : son codec est le codec markdown."""
    from docflow.documents import service as doc_svc
    from docflow.schemas.document import DocumentCreate

    created = await doc_svc.create_document(
        db_pool,
        "test-ws",
        DocumentCreate(
            title="Doc pour codec",
            block_id=test_block["id"],  # type: ignore[arg-type]
            content="# Bonjour",
        ),
    )
    async with db_pool.acquire() as conn:
        codec = await codec_for_document(conn, created.doc_technical_key)
    assert isinstance(codec, MarkdownCodec)


async def test_codec_for_document_inconnu_retombe_sur_le_repli(db_pool: asyncpg.Pool) -> None:
    """Document introuvable → repli, jamais d'exception."""
    async with db_pool.acquire() as conn:
        codec = await codec_for_document(conn, uuid.uuid4())
    assert codec is FALLBACK

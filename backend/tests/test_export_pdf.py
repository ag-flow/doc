"""Export PDF d'un document : assemblage HTML, ordre choisi, gardes."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.export.pdf import build_html, fetch_export_docs, strip_title_heading


def test_strip_title_heading_removes_exact_duplicate() -> None:
    assert strip_title_heading("# Titre\n\nCorps.", "Titre") == "Corps."
    # Titre différent : le heading reste (ce n'est pas un doublon).
    assert strip_title_heading("# Autre\n\nCorps.", "Titre").startswith("# Autre")


def test_build_html_orders_docs_and_breaks_pages() -> None:
    html = build_html(
        [("Racine", "Intro."), ("Enfant B", "B."), ("Enfant A", "A.")], signed=False
    )
    # Ordre EXACT reçu (celui choisi par l'utilisateur), pas alphabétique.
    assert html.index("Racine") < html.index("Enfant B") < html.index("Enfant A")
    # Saut de page avant chaque document suivant, pas avant le premier.
    assert html.count('class="doc doc-next"') == 2
    assert "Signatures" not in html


def test_build_html_signed_appends_signature_frame() -> None:
    html = build_html([("Doc", "x")], signed=True)
    assert "Signatures" in html
    assert html.index("Signatures") > html.index("Doc")


def test_build_html_escapes_title() -> None:
    html = build_html([("<script>", "x")], signed=False)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


async def _seed(pool: asyncpg.Pool) -> tuple[str, uuid.UUID, uuid.UUID, uuid.UUID]:
    slug = f"pdf-{uuid.uuid4().hex[:8]}"
    async with pool.acquire() as conn:
        wk = await conn.fetchval(
            "INSERT INTO workspace (slug, label) VALUES ($1, $2) "
            "RETURNING workspace_technical_key",
            slug,
            "PDF WS",
        )
        type_id = await conn.fetchval(
            "INSERT INTO functional_type (slug, label, workspace_technical_key) "
            "VALUES ('page', 'Page', $1) RETURNING id",
            wk,
        )
        block_id = await conn.fetchval(
            "INSERT INTO data_block (slug, label, functional_type_ref, "
            "workspace_technical_key) VALUES ('blk', 'Bloc', $1, $2) RETURNING id",
            type_id,
            wk,
        )

        async def _doc(title: str, content: str, parent: uuid.UUID | None) -> uuid.UUID:
            doc_id = await conn.fetchval(
                "INSERT INTO document (title, workspace_technical_key, parent, "
                "functional_type_ref, data_block_ref) "
                "VALUES ($1, $2, $3, $4, $5) RETURNING doc_technical_key",
                title,
                wk,
                parent,
                type_id,
                block_id,
            )
            await conn.execute(
                "INSERT INTO document_version (document_ref, version_number, title, content) "
                "VALUES ($1, 1, $2, $3)",
                doc_id,
                title,
                content,
            )
            return doc_id

        root = await _doc("Racine", "# Racine\n\nCorps racine.", None)
        child = await _doc("Enfant", "Corps enfant.", root)
        stranger = await _doc("Étranger", "Pas un enfant.", None)
    return slug, root, child, stranger


async def test_fetch_export_docs_orders_and_guards(db_pool: asyncpg.Pool) -> None:
    slug, root, child, stranger = await _seed(db_pool)

    filename, docs = await fetch_export_docs(db_pool, slug, root, [child])
    assert [d[0] for d in docs] == ["Racine", "Enfant"]
    assert filename  # slug du doc ou dérivé du titre

    # Un document qui n'est PAS un enfant direct : 422, aucun contournement.
    with pytest.raises(HTTPException) as exc:
        await fetch_export_docs(db_pool, slug, root, [stranger])
    assert exc.value.status_code == 422

    # Document racine inconnu : 404.
    with pytest.raises(HTTPException) as exc:
        await fetch_export_docs(db_pool, slug, uuid.uuid4(), [])
    assert exc.value.status_code == 404


async def test_render_pdf_end_to_end(db_pool: asyncpg.Pool) -> None:
    pytest.importorskip("weasyprint")
    from docflow.export.pdf import render_pdf

    slug, root, child, _ = await _seed(db_pool)
    _, docs = await fetch_export_docs(db_pool, slug, root, [child])
    pdf = render_pdf(build_html(docs, signed=True))
    assert pdf.startswith(b"%PDF-")

"""Tests spec 36 — MEXP : export markdown ZIP."""
from __future__ import annotations

import io
import zipfile

import asyncpg
import pytest

from docflow.export.service import build_export_zip
from docflow.schemas.document import DocumentCreate
from docflow.documents import service as doc_svc


async def test_export_workspace_returns_zip(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    ws = "test-ws"
    doc_a = await doc_svc.create_document(
        db_pool, ws, DocumentCreate(title="Doc Alpha", parent_id=None)
    )
    doc_b = await doc_svc.create_document(
        db_pool, ws, DocumentCreate(title="Doc Bêta", parent_id=None)
    )
    zip_bytes = await build_export_zip(db_pool, ws)
    assert len(zip_bytes) > 0
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = zf.namelist()
    # Les slugs attendus sont doc-alpha.md et doc-bta.md (normalisé)
    md_files = [n for n in names if n.endswith(".md")]
    assert len(md_files) >= 2


async def test_export_frontmatter_contains_docflow_id(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    ws = "test-ws"
    doc = await doc_svc.create_document(
        db_pool, ws, DocumentCreate(title="Doc Frontmatter", parent_id=None)
    )
    doc_id = str(doc.doc_technical_key)
    zip_bytes = await build_export_zip(db_pool, ws)
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    all_content = ""
    for name in zf.namelist():
        all_content += zf.read(name).decode()
    assert "docflow_id:" in all_content
    assert doc_id in all_content


async def test_export_link_rewrite(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Lien docflow:// interne réécrit en [[wikilink]]."""
    ws = "test-ws"
    doc_target = await doc_svc.create_document(
        db_pool, ws, DocumentCreate(title="Cible", parent_id=None)
    )
    target_id = doc_target.doc_technical_key
    content_with_link = f"Voir [Cible](docflow://doc/{target_id})"
    doc_src = await doc_svc.create_document(
        db_pool, ws, DocumentCreate(title="Source", parent_id=None, content=content_with_link)
    )
    zip_bytes = await build_export_zip(db_pool, ws)
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    all_content = ""
    for name in zf.namelist():
        all_content += zf.read(name).decode()
    assert "[[Cible]]" in all_content
    assert f"docflow://doc/{target_id}" not in all_content

from __future__ import annotations

import uuid

import asyncpg
import pytest

from docflow.references.parser import extract_references


# ── Parser (unitaire, sans DB) ────────────────────────────────────────────────


def test_extract_single_reference() -> None:
    md = "[Spec auth](docflow://doc/550e8400-e29b-41d4-a716-446655440000)"
    refs = extract_references(md)
    assert refs == {"550e8400-e29b-41d4-a716-446655440000": "Spec auth"}


def test_extract_multiple_references() -> None:
    md = (
        "[Doc A](docflow://doc/00000000-0000-0000-0000-000000000001) "
        "et [Doc B](docflow://doc/00000000-0000-0000-0000-000000000002)"
    )
    refs = extract_references(md)
    assert set(refs.keys()) == {
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    }


def test_extract_deduplicates_by_id_keeps_last_label() -> None:
    uid = "00000000-0000-0000-0000-000000000001"
    md = f"[Premier]({f'docflow://doc/{uid}'}) puis [Dernier]({f'docflow://doc/{uid}'})"
    refs = extract_references(md)
    assert refs == {uid: "Dernier"}


def test_extract_ignores_malformed_uuid() -> None:
    md = "[Bad](docflow://doc/not-a-uuid)"
    refs = extract_references(md)
    assert refs == {}


def test_extract_ignores_standard_links() -> None:
    md = "[Visit](https://example.com) [Doc](docflow://doc/550e8400-e29b-41d4-a716-446655440000)"
    refs = extract_references(md)
    assert list(refs.keys()) == ["550e8400-e29b-41d4-a716-446655440000"]


def test_extract_empty_markdown() -> None:
    assert extract_references("") == {}


def test_extract_no_links() -> None:
    assert extract_references("Texte sans lien.") == {}


def test_extract_empty_label() -> None:
    uid = "550e8400-e29b-41d4-a716-446655440000"
    md = f"[](docflow://doc/{uid})"
    refs = extract_references(md)
    assert refs == {uid: ""}


# ── Refresh + orphelins (nécessite DB) ───────────────────────────────────────


async def test_refresh_references_inserts(db_pool: asyncpg.Pool) -> None:
    """Le save insère les références extraites du contenu."""
    from docflow.references.service import refresh_references
    from docflow.schemas.workspace import WorkspaceCreate
    from docflow.workspaces import service as ws_svc
    from docflow.schemas.document import DocumentCreate
    from docflow.documents import service as doc_svc

    ws_slug = "ref-test-ins"
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug=ws_slug, label="Ref Ins"))
    try:
        async with db_pool.acquire() as conn:
            wk: uuid.UUID = await conn.fetchval(
                "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
            )

        # Crée deux documents (source et cible)
        source = await doc_svc.create_document(
            db_pool, ws_slug,
            DocumentCreate(title="Source", parent_id=None, functional_type_slug=None),
        )
        target = await doc_svc.create_document(
            db_pool, ws_slug,
            DocumentCreate(title="Cible", parent_id=None, functional_type_slug=None),
        )

        content = f"[Voir Cible](docflow://doc/{target.doc_technical_key})"

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await refresh_references(conn, source.doc_technical_key, wk, content)

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT target_ref, target_label FROM document_reference WHERE source_ref = $1",
                source.doc_technical_key,
            )
        assert len(rows) == 1
        assert rows[0]["target_ref"] == target.doc_technical_key
        assert rows[0]["target_label"] == "Voir Cible"
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", ws_slug)


async def test_refresh_references_replaces(db_pool: asyncpg.Pool) -> None:
    """Un lien retiré du contenu disparaît de la table au save suivant."""
    from docflow.references.service import refresh_references
    from docflow.schemas.workspace import WorkspaceCreate
    from docflow.workspaces import service as ws_svc
    from docflow.schemas.document import DocumentCreate
    from docflow.documents import service as doc_svc

    ws_slug = "ref-test-rep"
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug=ws_slug, label="Ref Rep"))
    try:
        async with db_pool.acquire() as conn:
            wk: uuid.UUID = await conn.fetchval(
                "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
            )

        source = await doc_svc.create_document(
            db_pool, ws_slug,
            DocumentCreate(title="Source", parent_id=None, functional_type_slug=None),
        )
        target = await doc_svc.create_document(
            db_pool, ws_slug,
            DocumentCreate(title="Cible", parent_id=None, functional_type_slug=None),
        )

        # Premier save : avec lien
        content_with = f"[Cible](docflow://doc/{target.doc_technical_key})"
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await refresh_references(conn, source.doc_technical_key, wk, content_with)

        # Deuxième save : lien retiré
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await refresh_references(conn, source.doc_technical_key, wk, "Texte sans lien.")

        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM document_reference WHERE source_ref = $1",
                source.doc_technical_key,
            )
        assert count == 0
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", ws_slug)


async def test_orphan_after_target_deleted(db_pool: asyncpg.Pool) -> None:
    """Supprimer la cible crée un orphelin sans bloquer la suppression."""
    from docflow.references.service import refresh_references, broken_links_by_bloc
    from docflow.schemas.workspace import WorkspaceCreate
    from docflow.workspaces import service as ws_svc
    from docflow.schemas.document import DocumentCreate
    from docflow.documents import service as doc_svc

    ws_slug = "ref-test-orp"
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug=ws_slug, label="Ref Orp"))
    try:
        async with db_pool.acquire() as conn:
            wk: uuid.UUID = await conn.fetchval(
                "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
            )

        source = await doc_svc.create_document(
            db_pool, ws_slug,
            DocumentCreate(title="Source", parent_id=None, functional_type_slug=None),
        )
        target = await doc_svc.create_document(
            db_pool, ws_slug,
            DocumentCreate(title="Cible", parent_id=None, functional_type_slug=None),
        )

        content = f"[Cible](docflow://doc/{target.doc_technical_key})"
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await refresh_references(conn, source.doc_technical_key, wk, content)

        # Supprime la cible — doit réussir (pas de FK dure)
        await doc_svc.delete_document(db_pool, ws_slug, target.doc_technical_key)

        # La référence est orpheline
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT r.target_ref, r.target_label
                FROM document_reference r
                LEFT JOIN document d ON d.doc_technical_key = r.target_ref
                WHERE r.source_ref = $1 AND d.doc_technical_key IS NULL
                """,
                source.doc_technical_key,
            )
        assert row is not None
        assert row["target_ref"] == target.doc_technical_key
        assert row["target_label"] == "Cible"

        # broken_links_by_bloc le signale
        blocs = await broken_links_by_bloc(db_pool, ws_slug)
        assert any(b.docs_with_broken_links >= 1 for b in blocs)
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", ws_slug)

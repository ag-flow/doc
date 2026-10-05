"""Recherche plein-texte globale (titre + contenu), cross-workspace, avec le
nom du workspace dans la réponse."""

from __future__ import annotations

import uuid

import asyncpg

from docflow.references.service import search_documents_global


async def _seed_doc(
    pool: asyncpg.Pool, ws_slug: str, ws_label: str, title: str, content: str
) -> uuid.UUID:
    wk = await pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) "
        "ON CONFLICT (slug) DO UPDATE SET label = EXCLUDED.label "
        "RETURNING workspace_technical_key",
        ws_slug,
        ws_label,
    )
    ft = await pool.fetchval(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ('page', 'Page', $1) ON CONFLICT DO NOTHING RETURNING id",
        wk,
    ) or await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'page'", wk
    )
    blk = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ('blk', 'Bloc', $1, $2) ON CONFLICT DO NOTHING RETURNING id",
        ft,
        wk,
    ) or await pool.fetchval(
        "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = 'blk'", wk
    )
    doc_id = await pool.fetchval(
        "INSERT INTO document (title, functional_type_ref, data_block_ref, "
        "workspace_technical_key, version) VALUES ($1, $2, $3, $4, 1) RETURNING doc_technical_key",
        title,
        ft,
        blk,
        wk,
    )
    await pool.execute(
        "INSERT INTO document_version (document_ref, version_number, title, content) "
        "VALUES ($1, 1, $2, $3)",
        doc_id,
        title,
        content,
    )
    return doc_id


async def test_fulltext_matches_content_and_returns_workspace_name(
    db_pool: asyncpg.Pool,
) -> None:
    try:
        await _seed_doc(
            db_pool, "ft-ws-a", "Espace A",
            title="Notes diverses",
            content="Le protocole Pickup gère les casiers logistiques.",
        )
        # Recherche sur un mot présent SEULEMENT dans le contenu (pas le titre).
        hits = await search_documents_global(db_pool, "casiers", 10, allowed_ws=None)
        assert [h.title for h in hits] == ["Notes diverses"]
        assert hits[0].workspace_slug == "ft-ws-a"
        assert hits[0].workspace_label == "Espace A"  # le NOM du workspace
        # url (ressource API), slug et révision.
        assert hits[0].url == f"/api/workspaces/ft-ws-a/documents/{hits[0].id}"
        assert hits[0].app_url == f"/ws/ft-ws-a/blocs/blk/documents/{hits[0].id}"
        assert hits[0].version == 1
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = 'ft-ws-a'")


async def test_fulltext_is_cross_workspace_and_scoped(db_pool: asyncpg.Pool) -> None:
    try:
        await _seed_doc(db_pool, "ft-ws-1", "WS 1", title="Rapport alpha", content="alpha")
        await _seed_doc(db_pool, "ft-ws-2", "WS 2", title="Rapport alpha", content="alpha")

        # allowed_ws=None (superadmin) → couvre TOUS les workspaces.
        all_hits = await search_documents_global(db_pool, "alpha", 10, allowed_ws=None)
        ws = {h.workspace_slug for h in all_hits}
        assert {"ft-ws-1", "ft-ws-2"} <= ws

        # Borné aux droits : un seul workspace autorisé → un seul résultat.
        scoped = await search_documents_global(db_pool, "alpha", 10, allowed_ws={"ft-ws-1"})
        assert {h.workspace_slug for h in scoped} == {"ft-ws-1"}

        # Aucun workspace autorisé → vide, fail closed.
        assert await search_documents_global(db_pool, "alpha", 10, allowed_ws=set()) == []
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = ANY($1)", ["ft-ws-1", "ft-ws-2"])

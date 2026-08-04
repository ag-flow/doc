from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException
from pydantic import BaseModel

from docflow.db.helpers import require_workspace
from docflow.references.parser import extract_references

# ── DTOs ─────────────────────────────────────────────────────────────────────


class DocumentSearchResult(BaseModel):
    id: uuid.UUID
    title: str
    type: str | None
    bloc: uuid.UUID | None


class BrokenLinkBloc(BaseModel):
    bloc: uuid.UUID | None
    docs_with_broken_links: int


class BrokenLinkDetail(BaseModel):
    source_ref: uuid.UUID
    source_title: str
    target_ref: uuid.UUID | None
    target_label: str


class BacklinkOut(BaseModel):
    source_id: uuid.UUID
    source_title: str
    source_type: str | None
    # Slug du data_block de la source (et non son UUID) : le front en a besoin pour
    # construire l'URL de navigation vers la source, qui peut appartenir à un autre bloc.
    bloc: str | None
    target_label: str


# ── Rafraîchissement des références (appelé dans la transaction du save) ─────


async def refresh_references(
    conn: asyncpg.Connection,
    doc_id: uuid.UUID,
    ws_key: uuid.UUID,
    content: str | None,
) -> None:
    """Remplace toutes les références du document.

    Doit être appelé dans la même transaction que le bump de version.
    La table est reconstruite à partir du contenu courant ; un lien retiré
    disparaît donc de la table au save suivant.
    """
    refs = extract_references(content or "")
    await conn.execute("DELETE FROM document_reference WHERE source_ref = $1", doc_id)
    if refs:
        await conn.executemany(
            """INSERT INTO document_reference
                   (source_ref, target_ref, target_label, workspace_technical_key)
               VALUES ($1, $2, $3, $4)""",
            [(doc_id, uuid.UUID(tid), label, ws_key) for tid, label in refs.items()],
        )


# ── Recherche de documents par titre ─────────────────────────────────────────


async def search_documents(
    pool: asyncpg.Pool,
    ws_slug: str,
    q: str,
    limit: int,
) -> list[DocumentSearchResult]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT d.doc_technical_key AS id,
                   d.title,
                   ft.slug             AS type,
                   d.data_block_ref    AS bloc
            FROM document d
            LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
            WHERE d.workspace_technical_key = $1
              AND d.title ILIKE '%' || $2 || '%'
            ORDER BY similarity(d.title, $2) DESC
            LIMIT $3
            """,
            wk,
            q,
            limit,
        )
    return [
        DocumentSearchResult(
            id=r["id"],
            title=r["title"],
            type=r["type"],
            bloc=r["bloc"],
        )
        for r in rows
    ]


# ── Détection d'orphelins ─────────────────────────────────────────────────────


async def broken_links_by_bloc(
    pool: asyncpg.Pool,
    ws_slug: str,
) -> list[BrokenLinkBloc]:
    """Agrégat par bloc : nombre de documents ayant ≥1 référence orpheline."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT src.data_block_ref                   AS bloc,
                   count(DISTINCT r.source_ref)::int    AS docs_with_broken_links
            FROM document_reference r
            JOIN document src        ON src.doc_technical_key = r.source_ref
            LEFT JOIN document target ON target.doc_technical_key = r.target_ref
            WHERE r.workspace_technical_key = $1
              AND target.doc_technical_key IS NULL
            GROUP BY src.data_block_ref
            """,
            wk,
        )
    return [
        BrokenLinkBloc(bloc=r["bloc"], docs_with_broken_links=r["docs_with_broken_links"])
        for r in rows
    ]


async def get_backlinks(
    pool: asyncpg.Pool,
    ws_slug: str,
    doc_id: uuid.UUID,
    limit: int = 50,
) -> list[BacklinkOut]:
    """Références inverses : documents qui citent doc_id dans ce workspace."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT r.source_ref            AS source_id,
                   src.title               AS source_title,
                   ft.slug                 AS source_type,
                   db.slug                 AS bloc,
                   r.target_label
            FROM document_reference r
            JOIN document src         ON src.doc_technical_key = r.source_ref
            JOIN data_block db        ON db.id = src.data_block_ref
            LEFT JOIN functional_type ft ON ft.id = src.functional_type_ref
            WHERE r.target_ref = $1
              AND r.workspace_technical_key = $2
            ORDER BY src.title
            LIMIT $3
            """,
            doc_id,
            wk,
            limit,
        )
    return [
        BacklinkOut(
            source_id=r["source_id"],
            source_title=r["source_title"],
            source_type=r["source_type"],
            bloc=r["bloc"],
            target_label=r["target_label"],
        )
        for r in rows
    ]


async def find_referencing_documents(
    pool: asyncpg.Pool,
    ws_slug: str,
    doc_id: uuid.UUID,
) -> list[dict[str, object]]:
    """Pages référençant doc_id, en fusionnant liens de contenu ET propriétés reference.

    Deux sources :
    - contenu : réutilise ``get_backlinks`` (table ``document_reference``) ;
    - propriété : valeur COURANTE d'une propriété de type ``reference`` pointant
      la cible (``properties_value_version.target_document_ref``).

    Dédup par (source_id, via, prop_slug|None), tri par ``source_title``.
    Lève 404 si ``doc_id`` n'appartient pas au workspace.
    """
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        exists = await conn.fetchval(
            "SELECT 1 FROM document WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
            doc_id,
            wk,
        )
        if exists is None:
            raise HTTPException(status_code=404, detail=f"document '{doc_id}' introuvable")
        prop_rows = await conn.fetch(
            """
            SELECT src.doc_technical_key AS source_id,
                   src.title             AS source_title,
                   db.slug               AS block_slug,
                   pd.slug               AS prop_slug
            FROM properties_values pv
            JOIN properties_value_version pvv
                   ON pvv.property_value_ref = pv.id
                  AND pvv.version_number = pv.version
            JOIN properties_defs pd  ON pd.id = pv.property_def_ref
            JOIN document src        ON src.doc_technical_key = pv.document_ref
            JOIN data_block db       ON db.id = src.data_block_ref
            WHERE pvv.target_document_ref = $1
              AND src.workspace_technical_key = $2
            """,
            doc_id,
            wk,
        )

    content = await get_backlinks(pool, ws_slug, doc_id)

    seen: set[tuple[str, str, str | None]] = set()
    items: list[dict[str, object]] = []
    for bl in content:
        key = (str(bl.source_id), "content", None)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "source_id": str(bl.source_id),
                "source_title": bl.source_title,
                "block_slug": bl.bloc,
                "via": "content",
                "label": bl.target_label,
            }
        )
    for r in prop_rows:
        key = (str(r["source_id"]), "property", r["prop_slug"])
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "source_id": str(r["source_id"]),
                "source_title": r["source_title"],
                "block_slug": r["block_slug"],
                "via": "property",
                "prop_slug": r["prop_slug"],
            }
        )
    items.sort(key=lambda it: str(it["source_title"]))
    return items


async def broken_links_detail(
    pool: asyncpg.Pool,
    ws_slug: str,
    bloc_id: uuid.UUID,
) -> list[BrokenLinkDetail]:
    """Détail des liens cassés d'un bloc : document source + libellé de la cible disparue."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT r.source_ref,
                   src.title   AS source_title,
                   r.target_ref,
                   r.target_label
            FROM document_reference r
            JOIN document src         ON src.doc_technical_key = r.source_ref
            LEFT JOIN document target  ON target.doc_technical_key = r.target_ref
            WHERE r.workspace_technical_key = $1
              AND src.data_block_ref = $2
              AND target.doc_technical_key IS NULL
            ORDER BY src.title
            """,
            wk,
            bloc_id,
        )
    return [
        BrokenLinkDetail(
            source_ref=r["source_ref"],
            source_title=r["source_title"],
            target_ref=r["target_ref"],
            target_label=r["target_label"],
        )
        for r in rows
    ]


class GlobalSearchResult(BaseModel):
    id: uuid.UUID
    title: str
    slug: str | None
    version: int
    url: str
    type: str | None
    workspace_slug: str
    workspace_label: str
    block_slug: str | None


async def search_documents_global(
    pool: asyncpg.Pool,
    q: str,
    limit: int,
    *,
    allowed_ws: set[str] | None,
) -> list[GlobalSearchResult]:
    """Recherche PLEIN-TEXTE (titre + contenu) sur TOUS les workspaces
    accessibles à l'appelant. Le contenu recherché est la version courante du
    document (document_version au version_number = document.version).

    ``allowed_ws=None`` = superadmin (aucun filtre) ; un ensemble vide renvoie
    une liste vide sans toucher la base (fail closed). Les correspondances de
    titre remontent avant celles trouvées seulement dans le contenu.
    """
    if allowed_ws is not None and not allowed_ws:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT d.doc_technical_key AS id,
                   d.title,
                   d.slug    AS slug,
                   d.version AS version,
                   ft.slug AS type,
                   w.slug  AS workspace_slug,
                   w.label AS workspace_label,
                   b.slug  AS block_slug
            FROM document d
            JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
            LEFT JOIN document_version dv
                 ON dv.document_ref = d.doc_technical_key
                AND dv.version_number = d.version
            LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
            LEFT JOIN data_block b ON b.id = d.data_block_ref
            WHERE (d.title ILIKE '%' || $1 || '%'
                   OR dv.content ILIKE '%' || $1 || '%')
              AND ($2::text[] IS NULL OR w.slug = ANY($2::text[]))
            ORDER BY (d.title ILIKE '%' || $1 || '%') DESC,
                     similarity(d.title, $1) DESC
            LIMIT $3
            """,
            q,
            sorted(allowed_ws) if allowed_ws is not None else None,
            limit,
        )
    return [
        GlobalSearchResult(
            id=r["id"],
            title=r["title"],
            slug=r["slug"],
            version=r["version"],
            # URL de ressource API canonique du document (miroir d'artifact_url).
            url=f"/api/workspaces/{r['workspace_slug']}/documents/{r['id']}",
            type=r["type"],
            workspace_slug=r["workspace_slug"],
            workspace_label=r["workspace_label"],
            block_slug=r["block_slug"],
        )
        for r in rows
    ]

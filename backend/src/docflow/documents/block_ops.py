"""Spec 23 — opérations sur l'arbre d'un bloc (allowed_types, list, create)."""

from __future__ import annotations

import uuid

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.documents.changelog import log_change
from docflow.schemas.document import DocumentCreateInBlock, DocumentOut

log = structlog.get_logger(__name__)

_SELECT_BLOCK_HEAD = """
SELECT d.doc_technical_key, d.title, d.type, d.version,
       d.parent, d.created_at, d.updated_at,
       d.data_block_ref,
       ft.slug AS functional_type_slug,
       w.slug  AS workspace_slug
FROM document d
JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
WHERE d.data_block_ref = $1
ORDER BY d.created_at
"""


def _row_head(row: asyncpg.Record) -> DocumentOut:
    return DocumentOut(
        doc_technical_key=row["doc_technical_key"],
        title=row["title"],
        type=row["type"],
        content=None,
        version=row["version"],
        parent_id=row["parent"],
        functional_type_slug=row["functional_type_slug"],
        workspace_slug=row["workspace_slug"],
        data_block_ref=row["data_block_ref"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _resolve_block_id(
    conn: asyncpg.Connection, wk: uuid.UUID, block_slug: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """Retourne (block_id, functional_type_ref) du bloc."""
    row = await conn.fetchrow(
        "SELECT id, functional_type_ref FROM data_block "
        "WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        block_slug,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
    return row["id"], row["functional_type_ref"]


async def _resolve_functional_type(conn: asyncpg.Connection, wk: uuid.UUID, slug: str) -> uuid.UUID:
    ft_id: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        slug,
    )
    if ft_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"type fonctionnel '{slug}' introuvable dans ce workspace",
        )
    return ft_id


async def _instantiate_default_values(
    conn: asyncpg.Connection,
    wk: uuid.UUID,
    doc_id: uuid.UUID,
    ft_id: uuid.UUID,
) -> None:
    """Instancie les valeurs par défaut pour les propriétés du type fonctionnel."""
    defs = await conn.fetch(
        "SELECT id, type, default_value FROM properties_defs "
        "WHERE functional_type_ref = $1 AND default_value IS NOT NULL",
        ft_id,
    )
    for pd in defs:
        prop_id: uuid.UUID = pd["id"]
        prop_type: str = pd["type"]
        default_val: str = pd["default_value"]

        allowed_value_ref: uuid.UUID | None = None
        value_to_store: str | None = None

        if prop_type == "restricted_list":
            allowed_value_ref = await conn.fetchval(
                "SELECT id FROM properties_allowed_values "
                "WHERE property_def_ref = $1 AND slug = $2",
                prop_id,
                default_val,
            )
            if allowed_value_ref is None:
                log.warning(
                    "default_value_not_found",
                    prop_id=str(prop_id),
                    default_val=default_val,
                )
                continue
        else:
            value_to_store = default_val

        pv_id: uuid.UUID = await conn.fetchval(
            "INSERT INTO properties_values "
            "(document_ref, property_def_ref, version, workspace_technical_key) "
            "VALUES ($1, $2, 1, $3) RETURNING id",
            doc_id,
            prop_id,
            wk,
        )
        await conn.execute(
            "INSERT INTO properties_value_version "
            "(property_value_ref, version_number, value, allowed_value_ref) "
            "VALUES ($1, 1, $2, $3)",
            pv_id,
            value_to_store,
            allowed_value_ref,
        )


async def allowed_types(
    pool: asyncpg.Pool,
    ws_slug: str,
    block_slug: str,
    parent_id: uuid.UUID | None = None,
) -> list[str]:
    """Retourne les slugs des types autorisés à la position donnée.

    Racine (parent_id=None) → [block.functional_type_slug]
    Sous parent_id → types dont parent = type du parent doc
    """
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        if parent_id is None:
            slug: str | None = await conn.fetchval(
                """
                SELECT ft.slug FROM functional_type ft
                JOIN data_block db ON db.functional_type_ref = ft.id
                WHERE db.id = (
                    SELECT id FROM data_block
                    WHERE workspace_technical_key = $1 AND slug = $2
                )
                """,
                wk,
                block_slug,
            )
            if slug is None:
                raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
            return [slug]
        else:
            rows = await conn.fetch(
                """
                SELECT ft.slug FROM functional_type ft
                WHERE ft.parent = (
                    SELECT d.functional_type_ref FROM document d WHERE d.doc_technical_key = $1
                )
                """,
                parent_id,
            )
            return [r["slug"] for r in rows]


async def list_block_documents(
    pool: asyncpg.Pool,
    ws_slug: str,
    block_slug: str,
    *,
    prop_slug: str | None = None,
    allowed_value_slug: str | None = None,
) -> list[DocumentOut]:
    """Tous les documents du bloc, à plat.

    Si prop_slug + allowed_value_slug fournis : filtre préservant le chemin
    (les ancêtres des nœuds retenus sont inclus dans le résultat).
    """
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        block_id, _ = await _resolve_block_id(conn, wk, block_slug)
        all_rows = await conn.fetch(_SELECT_BLOCK_HEAD, block_id)
        all_docs = [_row_head(r) for r in all_rows]

        if not (prop_slug and allowed_value_slug):
            return all_docs

        # Filtre : ids des docs dont la propriété a la valeur cherchée
        matched_ids: set[uuid.UUID] = set(
            r["document_ref"]
            for r in await conn.fetch(
                """
                SELECT pv.document_ref
                FROM properties_values pv
                JOIN properties_value_version pvv
                    ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
                JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
                JOIN properties_defs pd ON pd.id = pv.property_def_ref
                WHERE pv.document_ref = ANY(
                    SELECT doc_technical_key FROM document WHERE data_block_ref = $1
                )
                AND pd.slug  = $2
                AND pav.slug = $3
                """,
                block_id,
                prop_slug,
                allowed_value_slug,
            )
        )

        # Réintégration des ancêtres (filtre préservant le chemin)
        by_id = {d.doc_technical_key: d for d in all_docs}
        visible: set[uuid.UUID] = set(matched_ids)
        for mid in matched_ids:
            cur = by_id.get(mid)
            while cur and cur.parent_id:
                if cur.parent_id in visible:
                    break
                visible.add(cur.parent_id)
                cur = by_id.get(cur.parent_id)

        return [d for d in all_docs if d.doc_technical_key in visible]


async def list_block_values(
    pool: asyncpg.Pool, ws_slug: str, block_slug: str
) -> dict[str, list[dict[str, object]]]:
    """Valeurs courantes de toutes les propriétés pour tous les docs du bloc.

    Retourne {doc_id: [{prop_slug, type, value, allowed_value_slug, allowed_value_label}]}.
    Utilisé pour alimenter les colonnes dynamiques de la liste front.
    """
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        block_id, _ = await _resolve_block_id(conn, wk, block_slug)
        rows = await conn.fetch(
            """
            SELECT
                pv.document_ref,
                pd.slug  AS prop_slug,
                pd.type  AS prop_type,
                pvv.value,
                pav.slug AS allowed_value_slug,
                pav.label AS allowed_value_label,
                pav.color AS allowed_value_color
            FROM properties_values pv
            JOIN document d ON d.doc_technical_key = pv.document_ref
            JOIN properties_defs pd ON pd.id = pv.property_def_ref
            JOIN properties_value_version pvv
                ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
            LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
            WHERE d.data_block_ref = $1
            """,
            block_id,
        )

    result: dict[str, list[dict[str, object]]] = {}
    for r in rows:
        doc_key = str(r["document_ref"])
        result.setdefault(doc_key, []).append(
            {
                "prop_slug": r["prop_slug"],
                "prop_type": r["prop_type"],
                "value": r["value"],
                "allowed_value_slug": r["allowed_value_slug"],
                "allowed_value_label": r["allowed_value_label"],
                "allowed_value_color": r["allowed_value_color"],
            }
        )
    return result


async def create_document_in_block(
    pool: asyncpg.Pool,
    ws_slug: str,
    block_slug: str,
    body: DocumentCreateInBlock,
) -> DocumentOut:
    """Création deux temps : validate type autorisé → crée document v1 + valeurs par défaut."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            block_id, block_ft_ref = await _resolve_block_id(conn, wk, block_slug)

            # 1. Valider le parent (doit appartenir au même bloc)
            if body.parent_id is not None:
                parent_block: uuid.UUID | None = await conn.fetchval(
                    "SELECT data_block_ref FROM document WHERE doc_technical_key = $1",
                    body.parent_id,
                )
                if parent_block is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"document parent {body.parent_id} introuvable",
                    )
                if parent_block != block_id:
                    raise HTTPException(
                        status_code=422,
                        detail="le parent doit appartenir au même bloc",
                    )
                parent_wk: uuid.UUID | None = await conn.fetchval(
                    "SELECT workspace_technical_key FROM document WHERE doc_technical_key = $1",
                    body.parent_id,
                )
                if parent_wk != wk:
                    raise HTTPException(
                        status_code=422,
                        detail="le parent doit appartenir au même workspace (I-1)",
                    )

            # 2. Déterminer les types autorisés
            if body.parent_id is None:
                root_slug: str | None = await conn.fetchval(
                    "SELECT ft.slug FROM functional_type ft WHERE ft.id = $1",
                    block_ft_ref,
                )
                if root_slug is None:
                    raise HTTPException(
                        status_code=422,
                        detail="type fonctionnel du bloc introuvable",
                    )
                authorized: list[str] = [root_slug]
            else:
                auth_rows = await conn.fetch(
                    """
                    SELECT ft.slug FROM functional_type ft
                    WHERE ft.parent = (
                        SELECT d.functional_type_ref FROM document d
                        WHERE d.doc_technical_key = $1
                    )
                    """,
                    body.parent_id,
                )
                authorized = [r["slug"] for r in auth_rows]

            if not authorized:
                raise HTTPException(
                    status_code=422,
                    detail="position feuille : aucun type autorisé ici",
                )

            # 3. Résoudre le type final
            if body.functional_type_slug is None:
                if len(authorized) == 1:
                    chosen_slug = authorized[0]
                else:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"type_slug requis : plusieurs types possibles "
                            f"({', '.join(authorized)})"
                        ),
                    )
            else:
                if body.functional_type_slug not in authorized:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"type '{body.functional_type_slug}' non autorisé ici "
                            f"(autorisés : {', '.join(authorized)})"
                        ),
                    )
                chosen_slug = body.functional_type_slug

            ft_id = await _resolve_functional_type(conn, wk, chosen_slug)

            # 4. Créer le document
            row = await conn.fetchrow(
                """
                INSERT INTO document
                    (title, parent, functional_type_ref, workspace_technical_key, data_block_ref)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING doc_technical_key, title, type, version, parent,
                          data_block_ref, created_at, updated_at
                """,
                body.title,
                body.parent_id,
                ft_id,
                wk,
                block_id,
            )
            assert row is not None
            doc_id: uuid.UUID = row["doc_technical_key"]

            await conn.execute(
                "INSERT INTO document_version (document_ref, version_number, title, content) "
                "VALUES ($1, 1, $2, NULL)",
                doc_id,
                body.title,
            )

            # 5. Instancier les valeurs par défaut
            await _instantiate_default_values(conn, wk, doc_id, ft_id)

            # 6. Journaliser la création (spec 30)
            await log_change(conn, wk, doc_id, "C")

    return DocumentOut(
        doc_technical_key=row["doc_technical_key"],
        title=row["title"],
        type=row["type"],
        content=None,
        version=row["version"],
        parent_id=row["parent"],
        functional_type_slug=chosen_slug,
        workspace_slug=ws_slug,
        data_block_ref=row["data_block_ref"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

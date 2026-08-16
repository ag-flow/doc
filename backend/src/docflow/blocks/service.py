from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.documents.changelog import log_structure_change
from docflow.errors import DependentsConflictError
from docflow.schemas.block import DataBlockCreate, DataBlockOut, DataBlockUpdate

_SELECT_BLOCK = """
SELECT b.id, b.slug, b.label, b.created_at, b.updated_at, b.exposed,
       ft.slug  AS functional_type_slug,
       p.slug   AS parent_slug,
       w.slug   AS workspace_slug
FROM data_block b
JOIN workspace w ON w.workspace_technical_key = b.workspace_technical_key
JOIN functional_type ft ON ft.id = b.functional_type_ref
LEFT JOIN data_block p ON p.id = b.parent
WHERE b.workspace_technical_key = $1 AND b.slug = $2
"""

# Listing : volumétrie et dernière écriture par bloc, en sous-requêtes scalaires.
# Une lecture unitaire ne les paie pas — l'information n'a de sens qu'en liste.
_SELECT_ALL = """
SELECT b.id, b.slug, b.label, b.created_at, b.updated_at, b.exposed,
       ft.slug  AS functional_type_slug,
       p.slug   AS parent_slug,
       w.slug   AS workspace_slug,
       (SELECT count(*) FROM document d WHERE d.data_block_ref = b.id) AS documents_count,
       (SELECT max(d.updated_at) FROM document d WHERE d.data_block_ref = b.id) AS last_write_at
FROM data_block b
JOIN workspace w ON w.workspace_technical_key = b.workspace_technical_key
JOIN functional_type ft ON ft.id = b.functional_type_ref
LEFT JOIN data_block p ON p.id = b.parent
WHERE b.workspace_technical_key = $1
ORDER BY b.created_at
"""


def _row(row: asyncpg.Record) -> DataBlockOut:
    return DataBlockOut(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        functional_type_slug=row["functional_type_slug"],
        parent_slug=row["parent_slug"],
        workspace_slug=row["workspace_slug"],
        exposed=row["exposed"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        documents_count=row["documents_count"] if "documents_count" in row.keys() else 0,
        last_write_at=row["last_write_at"] if "last_write_at" in row.keys() else None,
    )


async def _resolve_type(
    conn: asyncpg.Connection, wk: uuid.UUID, type_slug: str
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """Retourne (type_id, type_parent_id)."""
    row = await conn.fetchrow(
        "SELECT id, parent FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        type_slug,
    )
    if row is None:
        raise HTTPException(
            status_code=422,
            detail=f"type fonctionnel '{type_slug}' introuvable dans ce workspace",
        )
    return row["id"], row["parent"]


async def _check_mirror_constraint(
    conn: asyncpg.Connection,
    wk: uuid.UUID,
    child_type_id: uuid.UUID,
    child_type_parent_id: uuid.UUID | None,
    parent_block_slug: str,
) -> None:
    """I-5 : le type de l'enfant doit être un fils direct du type du parent."""
    parent_row = await conn.fetchrow(
        "SELECT b.functional_type_ref FROM data_block b "
        "WHERE b.workspace_technical_key = $1 AND b.slug = $2",
        wk,
        parent_block_slug,
    )
    if parent_row is None:
        raise HTTPException(
            status_code=422,
            detail=f"bloc parent '{parent_block_slug}' introuvable dans ce workspace",
        )
    parent_type_id: uuid.UUID = parent_row["functional_type_ref"]
    if child_type_parent_id != parent_type_id:
        raise HTTPException(
            status_code=422,
            detail=(
                "contrainte miroir (I-5) : le type du bloc enfant doit être "
                "un fils direct du type du bloc parent"
            ),
        )


async def list_blocks(pool: asyncpg.Pool, ws_slug: str) -> list[DataBlockOut]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(_SELECT_ALL, wk)
    return [_row(r) for r in rows]


async def get_block(pool: asyncpg.Pool, ws_slug: str, block_slug: str) -> DataBlockOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(_SELECT_BLOCK, wk, block_slug)
    if row is None:
        raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
    return _row(row)


async def list_present_type_slugs(pool: asyncpg.Pool, ws_slug: str, block_slug: str) -> list[str]:
    """Slugs distincts des types fonctionnels réellement présents parmi les
    documents d'un bloc — pour dériver les colonnes de propriétés SANS charger
    tous les documents. Requête légère (DISTINCT indexé par bloc)."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT DISTINCT ft.slug AS slug
            FROM document d
            JOIN data_block b ON b.id = d.data_block_ref
            JOIN functional_type ft ON ft.id = d.functional_type_ref
            WHERE b.workspace_technical_key = $1 AND b.slug = $2
            ORDER BY ft.slug
            """,
            wk,
            block_slug,
        )
    return [r["slug"] for r in rows]


async def create_block(pool: asyncpg.Pool, ws_slug: str, data: DataBlockCreate) -> DataBlockOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            type_id, type_parent_id = await _resolve_type(conn, wk, data.functional_type_slug)

            parent_id: uuid.UUID | None = None
            if data.parent_slug is not None:
                await _check_mirror_constraint(conn, wk, type_id, type_parent_id, data.parent_slug)
                parent_id = await conn.fetchval(
                    "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = $2",
                    wk,
                    data.parent_slug,
                )
            else:
                # Bloc racine : le type doit être racine (parent=null dans functional_type)
                if type_parent_id is not None:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "contrainte miroir (I-5) : un bloc racine (sans parent) "
                            "doit avoir un type racine"
                        ),
                    )

            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO data_block
                        (slug, label, functional_type_ref, parent, workspace_technical_key)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, slug, label, created_at, updated_at
                    """,
                    data.slug,
                    data.label,
                    type_id,
                    parent_id,
                    wk,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"slug '{data.slug}' déjà utilisé dans ce workspace",
                ) from exc
            assert row is not None
            await log_structure_change(conn, wk, "block", "C", row["id"])
    return DataBlockOut(
        id=row["id"],
        slug=row["slug"],
        label=row["label"],
        functional_type_slug=data.functional_type_slug,
        parent_slug=data.parent_slug,
        workspace_slug=ws_slug,
        exposed=False,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def update_block(
    pool: asyncpg.Pool, ws_slug: str, block_slug: str, data: DataBlockUpdate
) -> DataBlockOut:
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        return await get_block(pool, ws_slug, block_slug)

    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            block_row = await conn.fetchrow(
                "SELECT id, functional_type_ref FROM data_block "
                "WHERE workspace_technical_key = $1 AND slug = $2",
                wk,
                block_slug,
            )
            if block_row is None:
                raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
            block_id: uuid.UUID = block_row["id"]
            block_type_id: uuid.UUID = block_row["functional_type_ref"]

            db_updates: dict[str, object] = {}
            if "label" in updates:
                db_updates["label"] = updates["label"]

            if "parent_slug" in updates:
                new_parent_slug = updates["parent_slug"]
                if new_parent_slug is not None:
                    type_parent_id: uuid.UUID | None = await conn.fetchval(
                        "SELECT parent FROM functional_type WHERE id = $1", block_type_id
                    )
                    await _check_mirror_constraint(
                        conn, wk, block_type_id, type_parent_id, new_parent_slug
                    )
                    db_updates["parent"] = await conn.fetchval(
                        "SELECT id FROM data_block "
                        "WHERE workspace_technical_key = $1 AND slug = $2",
                        wk,
                        new_parent_slug,
                    )
                else:
                    # Détachement à la racine : même contrainte miroir qu'à la
                    # création (I-5) — le type du bloc doit être racine.
                    type_parent_id = await conn.fetchval(
                        "SELECT parent FROM functional_type WHERE id = $1", block_type_id
                    )
                    if type_parent_id is not None:
                        raise HTTPException(
                            status_code=422,
                            detail=(
                                "contrainte miroir (I-5) : un bloc racine (sans parent) "
                                "doit avoir un type racine"
                            ),
                        )
                    db_updates["parent"] = None

            if not db_updates:
                return await get_block(pool, ws_slug, block_slug)

            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(db_updates))
            await conn.execute(
                f"UPDATE data_block SET {cols}, updated_at = now() WHERE id = $1",
                block_id,
                *list(db_updates.values()),
            )
            await log_structure_change(conn, wk, "block", "U", block_id)

    return await get_block(pool, ws_slug, block_slug)


async def set_block_exposed(
    pool: asyncpg.Pool, ws_slug: str, block_slug: str, value: bool
) -> DataBlockOut:
    """Expose ou masque le bloc entier et tous ses documents (en une transaction)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            block_id: uuid.UUID | None = await conn.fetchval(
                "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = $2",
                wk,
                block_slug,
            )
            if block_id is None:
                raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
            await conn.execute(
                "UPDATE data_block SET exposed = $2, updated_at = now() WHERE id = $1",
                block_id,
                value,
            )
            await conn.execute(
                "UPDATE document SET exposed = $2, updated_at = now() WHERE data_block_ref = $1",
                block_id,
                value,
            )
            await log_structure_change(conn, wk, "block", "U", block_id)
    return await get_block(pool, ws_slug, block_slug)


# DOC-07 : dépendants détruits par la cascade 0011 (data_block.parent CASCADE,
# document.data_block_ref CASCADE) = blocs descendants + documents du sous-arbre.
_COUNT_BLOCK_DEPENDENTS = """
WITH RECURSIVE subtree AS (
    SELECT id FROM data_block WHERE id = $1
    UNION ALL
    SELECT b.id FROM data_block b JOIN subtree s ON b.parent = s.id
)
SELECT (SELECT count(*) FROM subtree) - 1 AS child_blocks,
       (SELECT count(*) FROM document d
        WHERE d.data_block_ref IN (SELECT id FROM subtree)) AS documents
"""


async def count_block_dependents(
    pool: asyncpg.Pool, ws_slug: str, block_slug: str
) -> dict[str, int]:
    """Décompte des dépendants détruits par la cascade d'un delete_block.

    Retourne {"child_blocks": n, "documents": m}. Miroir applicatif de la garde
    de delete_block, exposé pour que la primitive MCP puisse afficher le décompte
    avant confirmation. Lève 404 si le bloc n'existe pas.
    """
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        block_id: uuid.UUID | None = await conn.fetchval(
            "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = $2",
            wk,
            block_slug,
        )
        if block_id is None:
            raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
        counts = await conn.fetchrow(_COUNT_BLOCK_DEPENDENTS, block_id)
        assert counts is not None
    return {"child_blocks": counts["child_blocks"], "documents": counts["documents"]}


async def delete_block(
    pool: asyncpg.Pool, ws_slug: str, block_slug: str, *, confirm: bool = False
) -> None:
    """Supprime un bloc.

    DOC-07 : la cascade 0011 détruit les blocs enfants et tous les documents du
    sous-arbre (valeurs et historique compris). On refuse (409) tant que
    ``confirm`` n'est pas fourni s'il existe des dépendants ; avec ``confirm``,
    la cascade DB est assumée.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            block_id: uuid.UUID | None = await conn.fetchval(
                "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = $2",
                wk,
                block_slug,
            )
            if block_id is None:
                raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
            counts = await conn.fetchrow(_COUNT_BLOCK_DEPENDENTS, block_id)
            assert counts is not None
            dependents = counts["child_blocks"] + counts["documents"]
            if dependents > 0 and not confirm:
                raise DependentsConflictError(
                    detail=(
                        f"la suppression du bloc '{block_slug}' détruirait en cascade "
                        f"{counts['child_blocks']} bloc(s) enfant(s) et "
                        f"{counts['documents']} document(s) (valeurs et historique compris) ; "
                        "repasser avec confirm=true pour confirmer la suppression"
                    ),
                    dependents=dependents,
                )
            await conn.execute("DELETE FROM data_block WHERE id = $1", block_id)
            await log_structure_change(conn, wk, "block", "D", block_id)

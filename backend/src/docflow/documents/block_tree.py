"""Mode browse arbre : `list_block_tree` (racines paginées + sous-arbres + valeurs).

Pagination sur les **racines** d'un bloc (≤100/page) ; chaque racine porte son
sous-arbre complet, assemblé depuis une CTE récursive suivant `document.parent`.
L'invariant DOC (un enfant hérite le bloc de son parent) garantit que tout le
sous-arbre d'une racine appartient au même bloc.

Réutilise les helpers de résolution/chargement de `block_query` — SQL 100 %
paramétré, aucun slug ni valeur interpolé dans la chaîne.
"""

from __future__ import annotations

import uuid
from typing import Literal

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.documents.block_query import _load_values, _resolve_block
from docflow.schemas.introspection import PropertyValueBrief
from docflow.schemas.tree import BlockTreeNode, BlockTreePage

TREE_DEFAULT_PAGE_SIZE = 50
TREE_MAX_PAGE_SIZE = 100

TreeSortKey = Literal["title", "updated_at"]
TreeSortDir = Literal["asc", "desc"]

# Colonnes de tri autorisées → expression SQL. Whitelist stricte : la clé de tri
# ne provient JAMAIS d'une chaîne utilisateur interpolée, seulement de cette table.
_SORT_COLUMNS: dict[str, str] = {"title": "title", "updated_at": "updated_at"}


def _tree_sql(sort_key: str, sort_dir: str) -> str:
    """Assemble la requête arbre avec un ordre de tri validé (whitelist).

    Racines paginées puis sous-arbres via récursion sur `parent`. L'ordre final
    (depth, <clé>, id) ordonne les racines et, dans chaque parent, les enfants
    par la même clé — l'assemblage `_build_tree` préserve cet ordre.
    """
    col = _SORT_COLUMNS[sort_key]  # KeyError impossible : clé validée en amont
    direction = "DESC" if sort_dir == "desc" else "ASC"
    nulls = " NULLS LAST" if sort_key == "updated_at" else ""
    order = f"{col} {direction}{nulls}"
    return f"""
WITH RECURSIVE roots AS (
    SELECT d.doc_technical_key
    FROM document d
    WHERE d.data_block_ref = $1 AND d.parent IS NULL
    ORDER BY d.{order}, d.doc_technical_key
    LIMIT $2 OFFSET $3
),
tree AS (
    SELECT d.doc_technical_key, d.title, d.parent, d.functional_type_ref,
           d.updated_at, d.updated_by, 0 AS depth
    FROM document d
    JOIN roots r ON r.doc_technical_key = d.doc_technical_key
    UNION ALL
    SELECT c.doc_technical_key, c.title, c.parent, c.functional_type_ref,
           c.updated_at, c.updated_by, t.depth + 1
    FROM document c
    JOIN tree t ON c.parent = t.doc_technical_key
)
SELECT t.doc_technical_key AS id, t.title, t.parent AS parent_id,
       t.updated_at, t.updated_by,
       ft.slug AS functional_type_slug, t.depth
FROM tree t
LEFT JOIN functional_type ft ON ft.id = t.functional_type_ref
ORDER BY t.depth, t.{order}, t.doc_technical_key
"""  # noqa: S608 — `order` est bâti depuis la whitelist _SORT_COLUMNS, pas d'entrée brute


def _normalize_pagination(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise HTTPException(status_code=422, detail="page doit être >= 1")
    if page_size < 1 or page_size > TREE_MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=422, detail=f"page_size doit être entre 1 et {TREE_MAX_PAGE_SIZE}"
        )
    return page, page_size


def _build_tree(
    block_slug: str,
    rows: list[asyncpg.Record],
    values: dict[uuid.UUID, list[PropertyValueBrief]],
    total: int,
    page: int,
    page_size: int,
) -> BlockTreePage:
    """Assemble les lignes plates (triées depth, title) en forêt de racines.

    Les lignes arrivant en ordre (depth, title), les racines et les enfants d'un
    même parent sont ajoutés en ordre de titre. Un nœud dont le parent n'est pas
    dans l'ensemble chargé (racine de la page) devient une racine.
    """
    nodes: dict[uuid.UUID, BlockTreeNode] = {}
    for r in rows:
        nodes[r["id"]] = BlockTreeNode(
            id=str(r["id"]),
            title=r["title"],
            functional_type_slug=r["functional_type_slug"],
            parent_id=str(r["parent_id"]) if r["parent_id"] is not None else None,
            updated_at=r["updated_at"],
            updated_by=r["updated_by"],
            properties=values.get(r["id"], []),
            children=[],
        )
    roots: list[BlockTreeNode] = []
    for r in rows:
        parent_id = r["parent_id"]
        if parent_id is not None and parent_id in nodes:
            nodes[parent_id].children.append(nodes[r["id"]])
        else:
            roots.append(nodes[r["id"]])
    return BlockTreePage(
        block_slug=block_slug,
        page=page,
        page_size=page_size,
        total=total,
        has_next=page * page_size < total,
        roots=roots,
    )


async def list_block_tree(
    pool: asyncpg.Pool,
    ws_slug: str,
    block_slug: str,
    page: int = 1,
    page_size: int = TREE_DEFAULT_PAGE_SIZE,
    sort_key: TreeSortKey = "title",
    sort_dir: TreeSortDir = "asc",
) -> BlockTreePage:
    """Racines paginées d'un bloc avec leurs sous-arbres et valeurs de propriétés.

    `sort_key`/`sort_dir` ordonnent racines et enfants côté serveur (tri correct
    à travers la pagination, contrairement à un tri client des seules pages chargées).
    """
    page, page_size = _normalize_pagination(page, page_size)
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        block_id = await _resolve_block(conn, wk, block_slug)
        total: int = await conn.fetchval(
            "SELECT count(*) FROM document WHERE data_block_ref = $1 AND parent IS NULL",
            block_id,
        )
        sql = _tree_sql(sort_key, sort_dir)
        rows = await conn.fetch(sql, block_id, page_size, (page - 1) * page_size)
        values = await _load_values(conn, [r["id"] for r in rows])
        return _build_tree(block_slug, list(rows), values, total, page, page_size)

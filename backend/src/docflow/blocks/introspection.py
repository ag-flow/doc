"""Introspection du schéma de propriétés d'un bloc, sans doc_id (épic MCP docflow).

Découverte dynamique : les slugs de propriétés et de statut sont propres à chaque
type. Cette primitive retourne, pour le type racine du bloc et ses descendants (les
seuls types instanciables dans le bloc), la définition des propriétés et — pour les
restricted_list — la liste des valeurs autorisées et le défaut. Aucun document requis.
"""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.schemas.introspection import (
    AllowedValueBrief,
    BlockPropertiesOut,
    BlockPropertyOut,
    BlockTypePropertiesOut,
)

# Type racine du bloc + tous ses descendants dans la hiérarchie des types.
_SUBTREE = """
WITH RECURSIVE subtree AS (
    SELECT id, slug, label, 0 AS depth
    FROM functional_type WHERE id = $1
    UNION ALL
    SELECT ft.id, ft.slug, ft.label, s.depth + 1
    FROM functional_type ft JOIN subtree s ON ft.parent = s.id
)
SELECT id, slug, label, depth FROM subtree ORDER BY depth, slug
"""

_DEFS = """
SELECT functional_type_ref AS ft_id, id, slug, label, type, required, default_value
FROM properties_defs
WHERE functional_type_ref = ANY($1::uuid[])
ORDER BY created_at
"""

_VALUES = """
SELECT property_def_ref, slug, label
FROM properties_allowed_values
WHERE property_def_ref = ANY($1::uuid[])
ORDER BY position, created_at
"""


async def list_block_properties(
    pool: asyncpg.Pool, ws_slug: str, block_slug: str
) -> BlockPropertiesOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        block = await conn.fetchrow(
            "SELECT b.functional_type_ref, ft.slug AS root_slug "
            "FROM data_block b JOIN functional_type ft ON ft.id = b.functional_type_ref "
            "WHERE b.workspace_technical_key = $1 AND b.slug = $2",
            wk,
            block_slug,
        )
        if block is None:
            raise HTTPException(status_code=404, detail=f"bloc '{block_slug}' introuvable")
        root_type_id: uuid.UUID = block["functional_type_ref"]

        types = await conn.fetch(_SUBTREE, root_type_id)
        type_ids = [t["id"] for t in types]
        defs = await conn.fetch(_DEFS, type_ids)
        def_ids = [d["id"] for d in defs]
        values = await conn.fetch(_VALUES, def_ids) if def_ids else []

    # Valeurs autorisées groupées par def.
    vals_by_def: dict[uuid.UUID, list[AllowedValueBrief]] = {}
    for v in values:
        vals_by_def.setdefault(v["property_def_ref"], []).append(
            AllowedValueBrief(slug=v["slug"], label=v["label"])
        )

    # Propriétés groupées par type.
    props_by_type: dict[uuid.UUID, list[BlockPropertyOut]] = {}
    for d in defs:
        allowed = vals_by_def.get(d["id"]) if d["type"] == "restricted_list" else None
        props_by_type.setdefault(d["ft_id"], []).append(
            BlockPropertyOut(
                prop_slug=d["slug"],
                label=d["label"],
                type=d["type"],
                required=d["required"],
                default_value=d["default_value"],
                allowed_values=allowed,
            )
        )

    type_blocks = [
        BlockTypePropertiesOut(
            functional_type_slug=t["slug"],
            label=t["label"],
            is_block_root=(t["id"] == root_type_id),
            properties=props_by_type.get(t["id"], []),
        )
        for t in types
    ]
    return BlockPropertiesOut(
        block_slug=block_slug,
        root_type_slug=block["root_slug"],
        types=type_blocks,
    )

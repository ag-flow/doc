"""Sérialisation YAML d'un bloc et du template de son type racine (git_sync).

Chaque répertoire de bloc exporté reçoit un `_block.yaml` : métadonnées du
bloc + sous-arbre de types du type racine (propriétés, contraintes, valeurs
autorisées), dans le même format que les templates importables — de quoi
recréer la structure à la main ou par import.

Lecture seule, aucune I/O disque : le contenu est écrit par la phase git.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import yaml

BLOCK_META_FILENAME = "_block.yaml"


async def _fetch_type_subtree(
    conn: asyncpg.Connection, root_type_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Types du sous-arbre (racine incluse), ordre parents-d'abord."""
    return [
        dict(r)
        for r in await conn.fetch(
            """
            WITH RECURSIVE subtree AS (
                SELECT id, slug, label, parent, 0 AS depth
                FROM functional_type WHERE id = $1
                UNION ALL
                SELECT t.id, t.slug, t.label, t.parent, s.depth + 1
                FROM functional_type t JOIN subtree s ON t.parent = s.id
            )
            SELECT id, slug, label, parent, depth FROM subtree ORDER BY depth, slug
            """,
            root_type_id,
        )
    ]


async def _serialize_properties(
    conn: asyncpg.Connection, type_id: uuid.UUID
) -> list[dict[str, Any]]:
    props: list[dict[str, Any]] = []
    for d in await conn.fetch(
        "SELECT id, slug, label, type, default_value, required, behavior"
        " FROM properties_defs WHERE functional_type_ref = $1 ORDER BY created_at",
        type_id,
    ):
        prop: dict[str, Any] = {"slug": d["slug"], "label": d["label"], "type": d["type"]}
        if d["default_value"] is not None:
            prop["default"] = d["default_value"]
        if d["required"]:
            prop["required"] = True
        if d["behavior"] is not None:
            prop["behavior"] = d["behavior"]
        constraints = [
            {"kind": c["kind"], "value": c["value"], "message": c["message"]}
            for c in await conn.fetch(
                "SELECT kind, value, message FROM properties_constraints"
                " WHERE property_def_ref = $1",
                d["id"],
            )
        ]
        if constraints:
            prop["constraints"] = constraints
        avs = [
            {
                "slug": a["slug"],
                "label": a["label"],
                "position": a["position"],
                **({"color": a["color"]} if a["color"] else {}),
            }
            for a in await conn.fetch(
                "SELECT slug, label, position, color FROM properties_allowed_values"
                " WHERE property_def_ref = $1 ORDER BY position, created_at",
                d["id"],
            )
        ]
        if avs:
            prop["allowed_values"] = avs
        props.append(prop)
    return props


async def block_meta_yaml(conn: asyncpg.Connection, block_id: uuid.UUID) -> str | None:
    """Contenu YAML du `_block.yaml` d'un bloc ; None si le bloc a disparu."""
    block = await conn.fetchrow(
        """
        SELECT b.slug, b.label, b.functional_type_ref, ft.slug AS type_slug
        FROM data_block b
        LEFT JOIN functional_type ft ON ft.id = b.functional_type_ref
        WHERE b.id = $1
        """,
        block_id,
    )
    if block is None:
        return None

    functional_types: list[dict[str, Any]] = []
    if block["functional_type_ref"] is not None:
        id_to_slug: dict[uuid.UUID, str] = {}
        for t in await _fetch_type_subtree(conn, block["functional_type_ref"]):
            id_to_slug[t["id"]] = t["slug"]
            entry: dict[str, Any] = {"slug": t["slug"], "label": t["label"]}
            parent_slug = id_to_slug.get(t["parent"]) if t["parent"] is not None else None
            if parent_slug is not None:
                entry["parent"] = parent_slug
            props = await _serialize_properties(conn, t["id"])
            if props:
                entry["properties"] = props
            functional_types.append(entry)

    meta = {
        "block": block["slug"],
        "label": block["label"],
        "type": block["type_slug"],
        "functional_types": functional_types,
    }
    return yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)

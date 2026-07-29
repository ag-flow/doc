"""Héritage à la création d'un type : copie matérialisée des propriétés.

Même sémantique que `inherit:` des templates — résolu UNE fois au moment de
la création, aucun lien vivant conservé (le méta-modèle n'a pas d'héritage
en base, c'est un choix de spec : pas de propagation surprise).
"""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import HTTPException

from docflow.documents.changelog import log_structure_change


async def resolve_inherit_source(
    conn: asyncpg.Connection, wk: uuid.UUID, inherit_slug: str
) -> uuid.UUID:
    """Résout le type source de l'héritage dans le même workspace (422 sinon)."""
    src: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM functional_type WHERE slug = $1 AND workspace_technical_key = $2",
        inherit_slug,
        wk,
    )
    if src is None:
        raise HTTPException(
            status_code=422, detail=f"type source '{inherit_slug}' introuvable"
        )
    return src


async def copy_properties(
    conn: asyncpg.Connection,
    src_type_id: uuid.UUID,
    dst_type_id: uuid.UUID,
    wk: uuid.UUID,
) -> None:
    """Copie les définitions de propriétés du type source vers le type cible :
    defs + contraintes + valeurs autorisées (couleurs et ordre compris)."""
    defs = await conn.fetch(
        "SELECT id, slug, label, type, default_value, required, "
        "       target_functional_type_ref, behavior "
        "FROM properties_defs WHERE functional_type_ref = $1",
        src_type_id,
    )
    for d in defs:
        new_id = await conn.fetchval(
            "INSERT INTO properties_defs "
            "(slug, label, functional_type_ref, type, default_value, required, "
            " target_functional_type_ref, behavior) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id",
            d["slug"],
            d["label"],
            dst_type_id,
            d["type"],
            d["default_value"],
            d["required"],
            d["target_functional_type_ref"],
            d["behavior"],
        )
        await conn.execute(
            "INSERT INTO properties_constraints (property_def_ref, kind, value, message) "
            "SELECT $1, kind, value, message FROM properties_constraints "
            "WHERE property_def_ref = $2",
            new_id,
            d["id"],
        )
        await conn.execute(
            "INSERT INTO properties_allowed_values "
            "(property_def_ref, slug, label, position, color) "
            "SELECT $1, slug, label, position, color FROM properties_allowed_values "
            "WHERE property_def_ref = $2",
            new_id,
            d["id"],
        )
        await log_structure_change(conn, wk, "property", "C", new_id)

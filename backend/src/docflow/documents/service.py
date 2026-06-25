from __future__ import annotations

import re
import uuid

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.schemas.document import DocumentCreate, DocumentOut, DocumentUpdate
from docflow.schemas.property_value import PropertyValueOut, PropertyValueSet

_SELECT_DOC = """
SELECT d.doc_technical_key, d.title, d.type, d.contenu,
       d.parent, d.created_at, d.updated_at,
       ft.slug AS functional_type_slug,
       w.slug  AS workspace_slug
FROM document d
JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
WHERE d.doc_technical_key = $1 AND d.workspace_technical_key = $2
"""

_SELECT_ALL = """
SELECT d.doc_technical_key, d.title, d.type, d.contenu,
       d.parent, d.created_at, d.updated_at,
       ft.slug AS functional_type_slug,
       w.slug  AS workspace_slug
FROM document d
JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
WHERE d.workspace_technical_key = $1
ORDER BY d.created_at
"""

_UPDATE_DOC = (
    "UPDATE document SET {cols}, updated_at = now() WHERE doc_technical_key = $1 "
    "RETURNING doc_technical_key, title, type, contenu, parent, created_at, updated_at"
)

_UPDATABLE = frozenset({"title", "contenu"})


def _row(row: asyncpg.Record) -> DocumentOut:
    return DocumentOut(
        doc_technical_key=row["doc_technical_key"],
        title=row["title"],
        type=row["type"],
        contenu=row["contenu"],
        parent_id=row["parent"],
        functional_type_slug=row["functional_type_slug"],
        workspace_slug=row["workspace_slug"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _resolve_functional_type(
    conn: asyncpg.Connection, wk: uuid.UUID, type_slug: str
) -> uuid.UUID:
    ft_id: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk, type_slug,
    )
    if ft_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"type fonctionnel '{type_slug}' introuvable dans ce workspace",
        )
    return ft_id


async def _validate_parent(
    conn: asyncpg.Connection, wk: uuid.UUID, parent_id: uuid.UUID
) -> None:
    """Vérifie que le parent existe et appartient au même workspace (I-1)."""
    parent_wk: uuid.UUID | None = await conn.fetchval(
        "SELECT workspace_technical_key FROM document WHERE doc_technical_key = $1",
        parent_id,
    )
    if parent_wk is None:
        raise HTTPException(
            status_code=422, detail=f"document parent {parent_id} introuvable"
        )
    if parent_wk != wk:
        raise HTTPException(
            status_code=422,
            detail="le parent doit appartenir au même workspace (I-1)",
        )


async def list_documents(pool: asyncpg.Pool, ws_slug: str) -> list[DocumentOut]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(_SELECT_ALL, wk)
    return [_row(r) for r in rows]


async def get_document(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID
) -> DocumentOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(_SELECT_DOC, doc_id, wk)
    if row is None:
        raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
    return _row(row)


async def create_document(
    pool: asyncpg.Pool, ws_slug: str, data: DocumentCreate
) -> DocumentOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            ft_id: uuid.UUID | None = None
            if data.functional_type_slug:
                ft_id = await _resolve_functional_type(conn, wk, data.functional_type_slug)
            if data.parent_id:
                await _validate_parent(conn, wk, data.parent_id)
            row = await conn.fetchrow(
                """
                INSERT INTO document
                    (title, contenu, parent, functional_type_ref, workspace_technical_key)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING doc_technical_key, title, type, contenu,
                          parent, created_at, updated_at
                """,
                data.title, data.contenu, data.parent_id, ft_id, wk,
            )
    assert row is not None
    ft_slug = data.functional_type_slug
    return DocumentOut(
        doc_technical_key=row["doc_technical_key"],
        title=row["title"],
        type=row["type"],
        contenu=row["contenu"],
        parent_id=row["parent"],
        functional_type_slug=ft_slug,
        workspace_slug=ws_slug,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def update_document(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, data: DocumentUpdate
) -> DocumentOut:
    raw = data.model_dump(exclude_unset=True)
    if not raw:
        return await get_document(pool, ws_slug, doc_id)

    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            exists: uuid.UUID | None = await conn.fetchval(
                "SELECT doc_technical_key FROM document "
                "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
                doc_id, wk,
            )
            if exists is None:
                raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")

            updates: dict[str, object] = {}
            for k, v in raw.items():
                if k in _UPDATABLE:
                    updates[k] = v

            if "parent_id" in raw:
                parent_id = raw["parent_id"]
                if parent_id is not None:
                    await _validate_parent(conn, wk, parent_id)
                updates["parent"] = parent_id

            if "functional_type_slug" in raw:
                ft_slug = raw["functional_type_slug"]
                if ft_slug is not None:
                    updates["functional_type_ref"] = await _resolve_functional_type(
                        conn, wk, ft_slug
                    )
                else:
                    updates["functional_type_ref"] = None

            if not updates:
                return await get_document(pool, ws_slug, doc_id)

            cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
            await conn.execute(
                _UPDATE_DOC.format(cols=cols), doc_id, *list(updates.values())
            )

    return await get_document(pool, ws_slug, doc_id)


async def delete_document(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            exists: uuid.UUID | None = await conn.fetchval(
                "SELECT doc_technical_key FROM document "
                "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
                doc_id, wk,
            )
            if exists is None:
                raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
            try:
                await conn.execute(
                    "DELETE FROM document WHERE doc_technical_key = $1", doc_id
                )
            except asyncpg.RestrictViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="impossible de supprimer : ce document a des enfants",
                ) from exc


# ── Property values ───────────────────────────────────────────────────────────


async def _get_doc_type_id(
    conn: asyncpg.Connection, wk: uuid.UUID, doc_id: uuid.UUID
) -> uuid.UUID:
    """Retourne le functional_type_ref du document, ou lève 422 si aucun."""
    row = await conn.fetchrow(
        "SELECT doc_technical_key, functional_type_ref FROM document "
        "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
        doc_id, wk,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
    if row["functional_type_ref"] is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "ce document n'a pas de type fonctionnel, "
                "impossible de lui attacher des valeurs"
            ),
        )
    ft_ref: uuid.UUID = row["functional_type_ref"]
    return ft_ref


async def _resolve_prop(
    conn: asyncpg.Connection, type_id: uuid.UUID, prop_slug: str
) -> tuple[uuid.UUID, str, bool, str | None]:
    """Retourne (prop_id, prop_type, required, prop_label) — I-2 : prop appartient au type."""
    row = await conn.fetchrow(
        "SELECT id, type, required, label, default_value "
        "FROM properties_defs WHERE functional_type_ref = $1 AND slug = $2",
        type_id, prop_slug,
    )
    if row is None:
        raise HTTPException(
            status_code=422,
            detail=f"propriété '{prop_slug}' inconnue pour ce type fonctionnel (I-2)",
        )
    return row["id"], row["type"], row["required"], row["label"]


def _validate_value_for_type(
    prop_type: str, data: PropertyValueSet, prop_slug: str
) -> None:
    """I-3 : text/int → value renseigné ; restricted_list → allowed_value_slug renseigné."""
    if prop_type in ("text", "int"):
        if data.value is None:
            raise HTTPException(
                status_code=422,
                detail=f"propriété '{prop_slug}' de type {prop_type} : 'value' requis",
            )
        if data.allowed_value_slug is not None:
            raise HTTPException(
                status_code=422,
                detail=f"propriété '{prop_slug}' de type {prop_type} : "
                "'allowed_value_slug' doit être null",
            )
    elif prop_type == "restricted_list":
        if data.allowed_value_slug is None:
            raise HTTPException(
                status_code=422,
                detail=f"propriété '{prop_slug}' de type restricted_list : "
                "'allowed_value_slug' requis",
            )
        if data.value is not None:
            raise HTTPException(
                status_code=422,
                detail=f"propriété '{prop_slug}' de type restricted_list : 'value' doit être null",
            )


async def _apply_constraints(
    conn: asyncpg.Connection, prop_id: uuid.UUID, prop_type: str, value: str | None
) -> None:
    """Applique les contraintes (min/max/min_length/max_length/pattern)."""
    rows = await conn.fetch(
        "SELECT kind, value, message FROM properties_constraints WHERE property_def_ref = $1",
        prop_id,
    )
    if not rows or value is None:
        return
    for r in rows:
        kind, cval, msg = r["kind"], r["value"], r["message"]
        error: str | None = None
        if kind == "min" and prop_type == "int":
            try:
                if int(value) < int(cval):
                    error = msg or f"valeur < minimum ({cval})"
            except ValueError:
                pass
        elif kind == "max" and prop_type == "int":
            try:
                if int(value) > int(cval):
                    error = msg or f"valeur > maximum ({cval})"
            except ValueError:
                pass
        elif kind == "min_length" and prop_type == "text":
            if len(value) < int(cval):
                error = msg or f"longueur < minimum ({cval})"
        elif kind == "max_length" and prop_type == "text":
            if len(value) > int(cval):
                error = msg or f"longueur > maximum ({cval})"
        elif kind == "pattern" and prop_type == "text":
            if not re.fullmatch(cval, value):
                error = msg or f"valeur ne correspond pas au pattern ({cval})"
        if error:
            raise HTTPException(status_code=422, detail=error)


async def _validate_int(value: str, prop_slug: str) -> None:
    try:
        int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"propriété '{prop_slug}' de type int : '{value}' n'est pas un entier",
        ) from exc


async def list_property_values(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID
) -> list[PropertyValueOut]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        type_id = await _get_doc_type_id(conn, wk, doc_id)
        rows = await conn.fetch(
            """
            SELECT pd.slug AS prop_slug, pd.label AS prop_label, pd.type, pd.required,
                   pd.default_value,
                   pv.value, pav.slug AS allowed_value_slug, pav.label AS allowed_value_label
            FROM properties_defs pd
            LEFT JOIN properties_values pv
                ON pv.property_def_ref = pd.id AND pv.document_ref = $2
            LEFT JOIN properties_allowed_values pav ON pav.id = pv.allowed_value_ref
            WHERE pd.functional_type_ref = $1
            ORDER BY pd.created_at
            """,
            type_id, doc_id,
        )
    return [
        PropertyValueOut(
            prop_slug=r["prop_slug"],
            prop_label=r["prop_label"],
            type=r["type"],
            value=r["value"] if r["value"] is not None else r["default_value"],
            allowed_value_slug=r["allowed_value_slug"],
            allowed_value_label=r["allowed_value_label"],
            required=r["required"],
        )
        for r in rows
    ]


async def set_property_value(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, prop_slug: str, data: PropertyValueSet
) -> PropertyValueOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            type_id = await _get_doc_type_id(conn, wk, doc_id)
            prop_id, prop_type, required, prop_label = await _resolve_prop(
                conn, type_id, prop_slug
            )
            _validate_value_for_type(prop_type, data, prop_slug)

            allowed_value_ref: uuid.UUID | None = None
            if prop_type == "int" and data.value is not None:
                await _validate_int(data.value, prop_slug)
            if prop_type == "restricted_list" and data.allowed_value_slug is not None:
                allowed_value_ref = await conn.fetchval(
                    "SELECT id FROM properties_allowed_values "
                    "WHERE property_def_ref = $1 AND slug = $2",
                    prop_id, data.allowed_value_slug,
                )
                if allowed_value_ref is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"valeur autorisée '{data.allowed_value_slug}' introuvable",
                    )

            if data.value is not None:
                await _apply_constraints(conn, prop_id, prop_type, data.value)

            await conn.execute(
                """
                INSERT INTO properties_values
                    (document_ref, property_def_ref, value,
                     allowed_value_ref, workspace_technical_key)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (document_ref, property_def_ref)
                DO UPDATE SET value = EXCLUDED.value,
                              allowed_value_ref = EXCLUDED.allowed_value_ref,
                              updated_at = now()
                """,
                doc_id, prop_id, data.value, allowed_value_ref, wk,
            )

    allowed_label: str | None = None
    if allowed_value_ref is not None:
        async with pool.acquire() as conn:
            allowed_label = await conn.fetchval(
                "SELECT label FROM properties_allowed_values WHERE id = $1", allowed_value_ref
            )
    return PropertyValueOut(
        prop_slug=prop_slug,
        prop_label=prop_label,
        type=prop_type,
        value=data.value,
        allowed_value_slug=data.allowed_value_slug,
        allowed_value_label=allowed_label,
        required=required,
    )


async def delete_property_value(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, prop_slug: str
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            type_id = await _get_doc_type_id(conn, wk, doc_id)
            prop_id, _, required, _ = await _resolve_prop(conn, type_id, prop_slug)
            if required:
                raise HTTPException(
                    status_code=422,
                    detail=f"propriété '{prop_slug}' est obligatoire (required), "
                    "impossible de supprimer sa valeur (I-4)",
                )
            deleted = await conn.fetchval(
                "DELETE FROM properties_values "
                "WHERE document_ref = $1 AND property_def_ref = $2 RETURNING id",
                doc_id, prop_id,
            )
            if deleted is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"aucune valeur pour la propriété '{prop_slug}' sur ce document",
                )

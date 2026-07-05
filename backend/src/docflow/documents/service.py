from __future__ import annotations

import datetime
import re
import urllib.parse
import uuid

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.documents import property_writes as prop_writes
from docflow.documents.block_ops import (
    allowed_types,
    create_document_in_block,
    list_block_documents,
)
from docflow.documents.changelog import log_change
from docflow.documents.template_apply import compute_initial_content
from docflow.references.service import refresh_references
from docflow.schemas.document import (
    DocumentCreate,
    DocumentOut,
    DocumentUpdate,
)
from docflow.schemas.property_value import PropertyValueOut, PropertyValueSet

log = structlog.get_logger(__name__)

# Spec 23 functions re-exported for callers importing from service
__all__ = [
    "allowed_types",
    "create_document_in_block",
    "list_block_documents",
]

# ── Lecture documents ─────────────────────────────────────────────────────────

_SELECT_HEAD = """
SELECT d.doc_technical_key, d.title, d.type, d.version,
       d.parent, d.created_at, d.updated_at,
       d.data_block_ref, d.exposed, d.slug,
       ft.slug AS functional_type_slug,
       w.slug  AS workspace_slug
FROM document d
JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
WHERE d.workspace_technical_key = $1
ORDER BY d.created_at
"""

_SELECT_DOC = """
SELECT d.doc_technical_key, d.title, d.type, d.version,
       d.parent, d.created_at, d.updated_at,
       d.data_block_ref, d.exposed, d.slug,
       ft.slug AS functional_type_slug,
       w.slug  AS workspace_slug,
       dv.content
FROM document d
JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
LEFT JOIN document_version dv
    ON dv.document_ref = d.doc_technical_key AND dv.version_number = d.version
WHERE d.doc_technical_key = $1 AND d.workspace_technical_key = $2
"""


def _row_head(row: asyncpg.Record) -> DocumentOut:
    return DocumentOut(
        doc_technical_key=row["doc_technical_key"],
        title=row["title"],
        type=row["type"],
        slug=row["slug"],
        content=None,
        version=row["version"],
        parent_id=row["parent"],
        functional_type_slug=row["functional_type_slug"],
        workspace_slug=row["workspace_slug"],
        data_block_ref=row["data_block_ref"],
        exposed=row["exposed"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_doc(row: asyncpg.Record) -> DocumentOut:
    return DocumentOut(
        doc_technical_key=row["doc_technical_key"],
        title=row["title"],
        type=row["type"],
        slug=row["slug"],
        content=row["content"],
        version=row["version"],
        parent_id=row["parent"],
        functional_type_slug=row["functional_type_slug"],
        workspace_slug=row["workspace_slug"],
        data_block_ref=row["data_block_ref"],
        exposed=row["exposed"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _resolve_functional_type(
    conn: asyncpg.Connection, wk: uuid.UUID, type_slug: str
) -> uuid.UUID:
    ft_id: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        type_slug,
    )
    if ft_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"type fonctionnel '{type_slug}' introuvable dans ce workspace",
        )
    return ft_id


async def _validate_parent(conn: asyncpg.Connection, wk: uuid.UUID, parent_id: uuid.UUID) -> None:
    parent_wk: uuid.UUID | None = await conn.fetchval(
        "SELECT workspace_technical_key FROM document WHERE doc_technical_key = $1",
        parent_id,
    )
    if parent_wk is None:
        raise HTTPException(status_code=422, detail=f"document parent {parent_id} introuvable")
    if parent_wk != wk:
        raise HTTPException(
            status_code=422,
            detail="le parent doit appartenir au même workspace (I-1)",
        )


async def _check_no_document_cycle(
    conn: asyncpg.Connection, doc_id: uuid.UUID, proposed_parent_id: uuid.UUID
) -> None:
    """Refuse un reparentage créant un cycle.

    Miroir de types/service.py::_check_no_cycle : refuse l'auto-parent et
    refuse si `doc_id` figure dans la chaîne d'ancêtres du nouveau parent
    (c.-à-d. si le nouveau parent est un descendant de doc_id). Prévient la
    boucle infinie de la CTE récursive de parcours d'arbre (DOC-02).
    """
    if proposed_parent_id == doc_id:
        raise HTTPException(
            status_code=422, detail="un document ne peut pas être son propre parent"
        )
    ancestor: uuid.UUID | None = proposed_parent_id
    while ancestor is not None:
        row = await conn.fetchrow(
            "SELECT parent FROM document WHERE doc_technical_key = $1", ancestor
        )
        if row is None:
            break
        if row["parent"] == doc_id:
            raise HTTPException(
                status_code=422, detail="cycle détecté dans la hiérarchie des documents"
            )
        ancestor = row["parent"]


async def _validate_type_position(
    conn: asyncpg.Connection,
    block_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    new_ft_id: uuid.UUID | None,
) -> None:
    """Revalide la position d'un document après changement de type (DOC-04).

    Racine du bloc (parent None) → le type doit être celui du bloc.
    Sous un parent → le type doit être un fils direct du type du parent.
    Un document sans type (new_ft_id None) n'est pas contraint.
    """
    if new_ft_id is None:
        return
    if parent_id is None:
        block_ft = await conn.fetchval(
            "SELECT functional_type_ref FROM data_block WHERE id = $1", block_id
        )
        if block_ft != new_ft_id:
            raise HTTPException(
                status_code=422,
                detail="type non autorisé à la racine de ce bloc (position)",
            )
    else:
        parent_ft = await conn.fetchval(
            "SELECT functional_type_ref FROM document WHERE doc_technical_key = $1",
            parent_id,
        )
        new_ft_parent = await conn.fetchval(
            "SELECT parent FROM functional_type WHERE id = $1", new_ft_id
        )
        if new_ft_parent != parent_ft:
            raise HTTPException(
                status_code=422,
                detail="type non autorisé sous ce parent (position)",
            )


async def _purge_orphan_property_values(
    conn: asyncpg.Connection, doc_id: uuid.UUID, new_ft_id: uuid.UUID | None
) -> None:
    """Supprime les valeurs de propriétés qui n'appartiennent plus au nouveau type (DOC-04).

    Purge transactionnelle : quand new_ft_id est None (type retiré), toutes les
    valeurs sont supprimées ; sinon seules celles dont la def n'est pas rattachée
    au nouveau type. La FK properties_value_version → properties_values cascade.
    """
    await conn.execute(
        "DELETE FROM properties_values "
        "WHERE document_ref = $1 "
        "AND property_def_ref NOT IN ("
        "    SELECT id FROM properties_defs WHERE functional_type_ref = $2"
        ")",
        doc_id,
        new_ft_id,
    )


async def list_documents(
    pool: asyncpg.Pool,
    ws_slug: str,
    *,
    functional_type: str | None = None,
    prop_slug: str | None = None,
    allowed_value_slug: str | None = None,
) -> list[DocumentOut]:
    """Arbre à plat — filtres optionnels pour le board.

    Quand functional_type + prop_slug + allowed_value_slug sont fournis,
    la jointure utilise idx_pvalue_version_allowed pour filtrer efficacement.
    """
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        if functional_type and prop_slug and allowed_value_slug:
            rows = await conn.fetch(
                """
                SELECT d.doc_technical_key, d.title, d.type, d.version,
                       d.parent, d.created_at, d.updated_at,
                       d.data_block_ref, d.exposed, d.slug,
                       ft.slug AS functional_type_slug,
                       w.slug  AS workspace_slug
                FROM document d
                JOIN workspace w  ON w.workspace_technical_key = d.workspace_technical_key
                JOIN functional_type ft ON ft.id = d.functional_type_ref
                JOIN properties_values pv ON pv.document_ref = d.doc_technical_key
                JOIN properties_value_version pvv
                    ON pvv.property_value_ref = pv.id
                    AND pvv.version_number    = pv.version
                JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
                JOIN properties_defs pd ON pd.id = pv.property_def_ref
                WHERE d.workspace_technical_key = $1
                  AND ft.slug  = $2
                  AND pd.slug  = $3
                  AND pav.slug = $4
                ORDER BY d.created_at
                """,
                wk,
                functional_type,
                prop_slug,
                allowed_value_slug,
            )
        elif functional_type:
            rows = await conn.fetch(
                """
                SELECT d.doc_technical_key, d.title, d.type, d.version,
                       d.parent, d.created_at, d.updated_at,
                       d.data_block_ref, d.exposed, d.slug,
                       ft.slug AS functional_type_slug,
                       w.slug  AS workspace_slug
                FROM document d
                JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
                JOIN functional_type ft ON ft.id = d.functional_type_ref
                WHERE d.workspace_technical_key = $1 AND ft.slug = $2
                ORDER BY d.created_at
                """,
                wk,
                functional_type,
            )
        else:
            rows = await conn.fetch(_SELECT_HEAD, wk)
    return [_row_head(r) for r in rows]


async def get_document(pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID) -> DocumentOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(_SELECT_DOC, doc_id, wk)
    if row is None:
        raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
    return _row_doc(row)


async def create_document(pool: asyncpg.Pool, ws_slug: str, data: DocumentCreate) -> DocumentOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            # Isolation workspace (DOC-03) : le bloc cible doit appartenir à ce workspace.
            block_ok = await conn.fetchval(
                "SELECT 1 FROM data_block WHERE id = $1 AND workspace_technical_key = $2",
                data.block_id,
                wk,
            )
            if not block_ok:
                raise HTTPException(
                    status_code=422,
                    detail="le bloc cible n'appartient pas à ce workspace",
                )
            ft_id: uuid.UUID | None = None
            if data.functional_type_slug:
                ft_id = await _resolve_functional_type(conn, wk, data.functional_type_slug)
            parent_exposed = False
            if data.parent_id:
                await _validate_parent(conn, wk, data.parent_id)
                parent_row = await conn.fetchrow(
                    "SELECT exposed, data_block_ref FROM document WHERE doc_technical_key = $1",
                    data.parent_id,
                )
                # Cohérence de l'arbre (DOC-03) : parent et enfant dans le même bloc.
                if parent_row is None or parent_row["data_block_ref"] != data.block_id:
                    raise HTTPException(
                        status_code=422,
                        detail="le parent doit appartenir au même bloc que le document",
                    )
                parent_exposed = bool(parent_row["exposed"])
            # Appliquer le template si corps vide et modèle défini
            initial_content = await compute_initial_content(conn, ft_id, data.title, data.content)
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO document
                        (title, slug, parent, functional_type_ref, workspace_technical_key,
                         data_block_ref, exposed)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING doc_technical_key, title, type, version, parent,
                              data_block_ref, exposed, slug, created_at, updated_at
                    """,
                    data.title,
                    data.slug,
                    data.parent_id,
                    ft_id,
                    wk,
                    data.block_id,
                    parent_exposed,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"slug '{data.slug}' déjà utilisé dans ce workspace",
                ) from exc
            assert row is not None
            await conn.execute(
                "INSERT INTO document_version (document_ref, version_number, title, content) "
                "VALUES ($1, 1, $2, $3)",
                row["doc_technical_key"],
                data.title,
                initial_content,
            )
            await log_change(conn, wk, row["doc_technical_key"], "C")
            await refresh_references(conn, row["doc_technical_key"], wk, initial_content)

            # Valeurs initiales de propriétés + contrat required (contrat dur :
            # la création échoue si une required sans default/behavior manque).
            new_doc_id: uuid.UUID = row["doc_technical_key"]
            if data.properties:
                if ft_id is None:
                    raise HTTPException(
                        status_code=422,
                        detail="properties fourni mais le document n'a pas de type fonctionnel",
                    )
                for prop_slug, prop_value in data.properties.items():
                    prop_id, prop_type, _, _, behavior = await _resolve_prop(conn, ft_id, prop_slug)
                    if behavior is not None:
                        raise HTTPException(
                            status_code=422,
                            detail=(
                                f"propriété '{prop_slug}' gérée automatiquement "
                                f"({behavior}) : écriture manuelle refusée"
                            ),
                        )
                    await prop_writes.upsert_value(
                        conn, wk, new_doc_id, prop_id, prop_type, prop_value, prop_slug
                    )
            if ft_id is not None:
                await prop_writes.apply_behaviors(conn, wk, new_doc_id, ft_id)
                await prop_writes.assert_required_satisfied(conn, new_doc_id, ft_id)
    return DocumentOut(
        doc_technical_key=row["doc_technical_key"],
        title=row["title"],
        type=row["type"],
        slug=row["slug"],
        content=initial_content,
        version=row["version"],
        parent_id=row["parent"],
        functional_type_slug=data.functional_type_slug,
        workspace_slug=ws_slug,
        data_block_ref=row["data_block_ref"],
        exposed=row["exposed"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def update_document(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, data: DocumentUpdate
) -> DocumentOut:
    raw = data.model_dump(exclude_unset=True)
    if not raw:
        return await get_document(pool, ws_slug, doc_id)

    has_content = "title" in raw or "content" in raw
    if has_content and data.expected_version is None:
        raise HTTPException(
            status_code=422,
            detail="expected_version requis pour modifier le titre ou le contenu",
        )

    # Verrouiller la ligne dès qu'on touche au contenu OU au parent (anti-cycle DOC-02).
    lock_row = has_content or "parent_id" in raw

    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug, allow_archived=False)

            # Existence + verrou optimiste
            head = await conn.fetchrow(
                "SELECT version, title, functional_type_ref, parent, data_block_ref "
                "FROM document "
                "WHERE doc_technical_key = $1 AND workspace_technical_key = $2"
                + (" FOR UPDATE" if lock_row else ""),
                doc_id,
                wk,
            )
            if head is None:
                raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")

            if has_content:
                current_v = head["version"]
                if current_v != data.expected_version:
                    cur = await conn.fetchrow(
                        "SELECT content FROM document_version "
                        "WHERE document_ref = $1 AND version_number = $2",
                        doc_id,
                        current_v,
                    )
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "version": current_v,
                            "title": head["title"],
                            "content": cur["content"] if cur else None,
                        },
                    )
                new_v = current_v + 1
                new_title = raw.get("title", head["title"])
                if "content" not in raw:
                    prev = await conn.fetchrow(
                        "SELECT content FROM document_version "
                        "WHERE document_ref = $1 AND version_number = $2",
                        doc_id,
                        current_v,
                    )
                    new_content: str | None = prev["content"] if prev else None
                else:
                    new_content = raw.get("content")
                await conn.execute(
                    "INSERT INTO document_version (document_ref, version_number, title, content) "
                    "VALUES ($1, $2, $3, $4)",
                    doc_id,
                    new_v,
                    new_title,
                    new_content,
                )
                await conn.execute(
                    "UPDATE document SET version = $1, title = $2, updated_at = now() "
                    "WHERE doc_technical_key = $3",
                    new_v,
                    new_title,
                    doc_id,
                )
                await log_change(conn, wk, doc_id, "U")
                await refresh_references(conn, doc_id, wk, new_content)

            # Métadonnées (parent, type, slug) — sans versioning
            meta: dict[str, object] = {}
            reparented = "parent_id" in raw
            if reparented:
                pid = raw["parent_id"]
                if pid is not None:
                    await _validate_parent(conn, wk, pid)
                    await _check_no_document_cycle(conn, doc_id, pid)
                    # Cohérence de l'arbre (miroir DOC-03 du create) : parent
                    # et enfant dans le même bloc.
                    parent_block = await conn.fetchval(
                        "SELECT data_block_ref FROM document WHERE doc_technical_key = $1",
                        pid,
                    )
                    if parent_block != head["data_block_ref"]:
                        raise HTTPException(
                            status_code=422,
                            detail="le parent doit appartenir au même bloc que le document",
                        )
                meta["parent"] = pid
            retyped = "functional_type_slug" in raw
            new_ft_id: uuid.UUID | None = head["functional_type_ref"]
            if retyped:
                ft_slug = raw["functional_type_slug"]
                new_ft_id = None
                if ft_slug is not None:
                    new_ft_id = await _resolve_functional_type(conn, wk, ft_slug)
                meta["functional_type_ref"] = new_ft_id
            # DOC-04 : revalider la position dès que le parent OU le type change —
            # un reparentage seul peut invalider le type courant (à la racine le
            # type doit être celui du bloc ; sous un parent, un fils direct du
            # type du parent). Refus explicite plutôt qu'invariant violé en silence.
            type_changed = retyped and new_ft_id != head["functional_type_ref"]
            if reparented or type_changed:
                effective_parent = raw["parent_id"] if reparented else head["parent"]
                try:
                    await _validate_type_position(
                        conn, head["data_block_ref"], effective_parent, new_ft_id
                    )
                except HTTPException as exc:
                    if reparented and not retyped:
                        raise HTTPException(
                            status_code=422,
                            detail=(
                                "reparentage refusé : le type actuel du document n'est pas "
                                "autorisé à cette position — re-préciser functional_type_slug "
                                "(type du bloc à la racine, type fils du type du parent sinon) "
                                "dans la même requête"
                            ),
                        ) from exc
                    raise
            if type_changed:
                await _purge_orphan_property_values(conn, doc_id, new_ft_id)
            if "slug" in raw:
                meta["slug"] = raw["slug"]
            if meta:
                cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(meta))
                try:
                    await conn.execute(
                        f"UPDATE document SET {cols}, updated_at = now() "  # noqa: S608
                        "WHERE doc_technical_key = $1",
                        doc_id,
                        *list(meta.values()),
                    )
                except asyncpg.UniqueViolationError as exc:
                    if "slug" in raw:
                        detail = f"slug '{raw['slug']}' déjà utilisé dans ce workspace"
                    else:
                        detail = "un document avec le même slug existe déjà sous le parent visé"
                    raise HTTPException(status_code=409, detail=detail) from exc
                # Les sessions actives doivent voir les déplacements/retypages :
                # une mutation de métadonnées alimente aussi le change feed.
                await log_change(conn, wk, doc_id, "U")

            # Contrat dur + comportements : tout enregistrement vaut révision.
            # auto_now est reposée ; après un changement de type, les required
            # du nouveau type doivent être satisfaits (valeur, default ou
            # behavior) — sinon refus 422 listant les manquants.
            mutated = bool(meta) or "content" in raw or "title" in raw
            if mutated:
                effective_ft: uuid.UUID | None = (
                    new_ft_id if retyped else head["functional_type_ref"]
                )
                await prop_writes.apply_behaviors(conn, wk, doc_id, effective_ft)
                if type_changed and effective_ft is not None:
                    await prop_writes.assert_required_satisfied(conn, doc_id, effective_ft)

    return await get_document(pool, ws_slug, doc_id)


async def delete_document(pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID) -> dict[str, object]:
    """Supprime le document et tous ses descendants (ON DELETE CASCADE sur document.parent).

    Retourne un snapshot {id, title, type} capturé avant suppression.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            snap = await conn.fetchrow(
                "SELECT doc_technical_key, title, type FROM document "
                "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
                doc_id,
                wk,
            )
            if snap is None:
                raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
            await conn.execute("DELETE FROM document WHERE doc_technical_key = $1", doc_id)
            await log_change(conn, wk, doc_id, "D")
    return {"id": str(snap["doc_technical_key"]), "title": snap["title"], "type": snap["type"]}


async def set_document_exposed(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, value: bool
) -> DocumentOut:
    """Expose ou masque le document et tous ses descendants (cascade récursive)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            exists = await conn.fetchval(
                "SELECT 1 FROM document "
                "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
                doc_id,
                wk,
            )
            if not exists:
                raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
            await conn.execute(
                """
                WITH RECURSIVE descendants AS (
                    SELECT doc_technical_key
                    FROM document
                    WHERE doc_technical_key = $1
                    UNION ALL
                    SELECT d.doc_technical_key
                    FROM document d
                    JOIN descendants p ON d.parent = p.doc_technical_key
                )
                UPDATE document SET exposed = $2, updated_at = now()
                WHERE doc_technical_key IN (SELECT doc_technical_key FROM descendants)
                """,
                doc_id,
                value,
            )
    return await get_document(pool, ws_slug, doc_id)


# ── Property values ───────────────────────────────────────────────────────────


async def _get_doc_type_id(conn: asyncpg.Connection, wk: uuid.UUID, doc_id: uuid.UUID) -> uuid.UUID:
    row = await conn.fetchrow(
        "SELECT doc_technical_key, functional_type_ref FROM document "
        "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
        doc_id,
        wk,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
    if row["functional_type_ref"] is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "ce document n'a pas de type fonctionnel, impossible de lui attacher des valeurs"
            ),
        )
    ft_ref: uuid.UUID = row["functional_type_ref"]
    return ft_ref


async def _resolve_prop(
    conn: asyncpg.Connection, type_id: uuid.UUID, prop_slug: str
) -> tuple[uuid.UUID, str, bool, str, str | None]:
    row = await conn.fetchrow(
        "SELECT id, type, required, label, behavior "
        "FROM properties_defs WHERE functional_type_ref = $1 AND slug = $2",
        type_id,
        prop_slug,
    )
    if row is None:
        raise HTTPException(
            status_code=422,
            detail=f"propriété '{prop_slug}' inconnue pour ce type fonctionnel (I-2)",
        )
    return row["id"], row["type"], row["required"], row["label"], row["behavior"]


_SCALAR_TYPES = frozenset({"text", "int", "date", "bool", "url", "float"})


def _validate_value_for_type(prop_type: str, data: PropertyValueSet, prop_slug: str) -> None:
    if prop_type in _SCALAR_TYPES:
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
    elif prop_type == "reference":
        if data.value is None:
            raise HTTPException(
                status_code=422,
                detail=f"propriété '{prop_slug}' de type reference : 'value' (doc UUID) requis",
            )
        if data.allowed_value_slug is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"propriété '{prop_slug}' de type reference : "
                    "'allowed_value_slug' doit être null"
                ),
            )
        try:
            import uuid as _uuid

            _uuid.UUID(data.value)
        except (ValueError, AttributeError) as exc:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"propriété '{prop_slug}' de type reference : "
                    f"'{data.value}' n'est pas un UUID valide"
                ),
            ) from exc


async def _apply_constraints(
    conn: asyncpg.Connection, prop_id: uuid.UUID, prop_type: str, value: str
) -> None:
    rows = await conn.fetch(
        "SELECT kind, value, message FROM properties_constraints WHERE property_def_ref = $1",
        prop_id,
    )
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
        elif kind == "min" and prop_type == "float":
            try:
                if float(value) < float(cval):
                    error = msg or f"valeur < minimum ({cval})"
            except ValueError:
                pass
        elif kind == "max" and prop_type == "float":
            try:
                if float(value) > float(cval):
                    error = msg or f"valeur > maximum ({cval})"
            except ValueError:
                pass
        elif kind == "min" and prop_type == "date":
            try:
                if datetime.date.fromisoformat(value) < datetime.date.fromisoformat(cval):
                    error = msg or f"date antérieure au minimum ({cval})"
            except ValueError:
                pass
        elif kind == "max" and prop_type == "date":
            try:
                if datetime.date.fromisoformat(value) > datetime.date.fromisoformat(cval):
                    error = msg or f"date postérieure au maximum ({cval})"
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


def _validate_date(value: str, prop_slug: str) -> None:
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"propriété '{prop_slug}' de type date : "
                f"'{value}' n'est pas une date ISO (YYYY-MM-DD)"
            ),
        ) from exc


def _validate_bool(value: str, prop_slug: str) -> None:
    if value not in {"true", "false"}:
        raise HTTPException(
            status_code=422,
            detail=(
                f"propriété '{prop_slug}' de type bool : '{value}' invalide "
                "— valeurs acceptées : 'true' ou 'false'"
            ),
        )


def _validate_url(value: str, prop_slug: str) -> None:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"propriété '{prop_slug}' de type url : "
                "URL invalide (scheme http/https requis, netloc requis)"
            ),
        )


def _validate_float(value: str, prop_slug: str) -> None:
    try:
        float(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"propriété '{prop_slug}' de type float : '{value}' n'est pas un nombre décimal",
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
                   pd.behavior, pd.default_value,
                   pv.version AS pv_version,
                   pvv.value,
                   pav.slug AS allowed_value_slug, pav.label AS allowed_value_label
            FROM properties_defs pd
            LEFT JOIN properties_values pv
                ON pv.property_def_ref = pd.id AND pv.document_ref = $2
            LEFT JOIN properties_value_version pvv
                ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
            LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
            WHERE pd.functional_type_ref = $1
            ORDER BY pd.created_at
            """,
            type_id,
            doc_id,
        )
    result = []
    for r in rows:
        if r["pv_version"] is None:
            val = r["default_value"]
            av_slug = None
            av_label = None
        else:
            val = r["value"]
            av_slug = r["allowed_value_slug"]
            av_label = r["allowed_value_label"]
        result.append(
            PropertyValueOut(
                prop_slug=r["prop_slug"],
                prop_label=r["prop_label"],
                type=r["type"],
                version=r["pv_version"],
                value=val,
                allowed_value_slug=av_slug,
                allowed_value_label=av_label,
                required=r["required"],
                behavior=r["behavior"],
            )
        )
    return result


async def set_property_value(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, prop_slug: str, data: PropertyValueSet
) -> PropertyValueOut:
    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            type_id = await _get_doc_type_id(conn, wk, doc_id)
            prop_id, prop_type, required, prop_label, behavior = await _resolve_prop(
                conn, type_id, prop_slug
            )
            if behavior is not None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"propriété '{prop_slug}' gérée automatiquement ({behavior}) : "
                        "écriture manuelle refusée"
                    ),
                )
            _validate_value_for_type(prop_type, data, prop_slug)

            allowed_value_ref: uuid.UUID | None = None
            if prop_type == "int" and data.value is not None:
                await _validate_int(data.value, prop_slug)
            if prop_type == "date" and data.value is not None:
                _validate_date(data.value, prop_slug)
            if prop_type == "bool" and data.value is not None:
                _validate_bool(data.value, prop_slug)
            if prop_type == "url" and data.value is not None:
                _validate_url(data.value, prop_slug)
            if prop_type == "float" and data.value is not None:
                _validate_float(data.value, prop_slug)
            if prop_type == "restricted_list" and data.allowed_value_slug is not None:
                allowed_value_ref = await conn.fetchval(
                    "SELECT id FROM properties_allowed_values "
                    "WHERE property_def_ref = $1 AND slug = $2",
                    prop_id,
                    data.allowed_value_slug,
                )
                if allowed_value_ref is None:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"valeur autorisée '{data.allowed_value_slug}' introuvable "
                            "ou n'appartient pas à cette définition (I-5)"
                        ),
                    )
            if prop_type == "reference" and data.value is not None:
                ref_doc_id = uuid.UUID(data.value)
                # Vérifier que le doc cible existe dans ce workspace
                exists = await conn.fetchval(
                    "SELECT 1 FROM document "
                    "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
                    ref_doc_id,
                    wk,
                )
                if not exists:
                    raise HTTPException(
                        status_code=422,
                        detail=f"document cible '{data.value}' introuvable dans ce workspace",
                    )
                # Vérifier le type cible (target_functional_type_ref) si défini
                target_ft_id = await conn.fetchval(
                    "SELECT target_functional_type_ref FROM properties_defs WHERE id = $1",
                    prop_id,
                )
                if target_ft_id is not None:
                    doc_ft_id = await conn.fetchval(
                        "SELECT functional_type_ref FROM document WHERE doc_technical_key = $1",
                        ref_doc_id,
                    )
                    if doc_ft_id != target_ft_id:
                        raise HTTPException(
                            status_code=422,
                            detail=(
                                "le document cible n'est pas du type fonctionnel attendu "
                                "(contrainte target_functional_type_ref)"
                            ),
                        )
            if data.value is not None:
                await _apply_constraints(conn, prop_id, prop_type, data.value)

            # ── Verrou optimiste ──
            pv_row = await conn.fetchrow(
                "SELECT id, version FROM properties_values "
                "WHERE document_ref = $1 AND property_def_ref = $2 FOR UPDATE",
                doc_id,
                prop_id,
            )

            if pv_row is None:
                if data.expected_version != 0:
                    raise HTTPException(
                        status_code=409,
                        detail={"version": 0, "value": None, "allowed_value_slug": None},
                    )
                try:
                    pv_id: uuid.UUID = await conn.fetchval(
                        "INSERT INTO properties_values "
                        "(document_ref, property_def_ref, version, workspace_technical_key) "
                        "VALUES ($1, $2, 1, $3) RETURNING id",
                        doc_id,
                        prop_id,
                        wk,
                    )
                except asyncpg.UniqueViolationError as exc:
                    raise HTTPException(
                        status_code=409,
                        detail={"version": 0, "value": None, "allowed_value_slug": None},
                    ) from exc
                target_doc_ref: uuid.UUID | None = (
                    uuid.UUID(data.value) if prop_type == "reference" and data.value else None
                )
                await conn.execute(
                    "INSERT INTO properties_value_version "
                    "(property_value_ref, version_number, "
                    "value, allowed_value_ref, target_document_ref) "
                    "VALUES ($1, 1, $2, $3, $4)",
                    pv_id,
                    data.value,
                    allowed_value_ref,
                    target_doc_ref,
                )
                return_version = 1
            else:
                current_v: int = pv_row["version"]
                if current_v != data.expected_version:
                    cur = await conn.fetchrow(
                        "SELECT pvv.value, pav.slug AS allowed_value_slug "
                        "FROM properties_value_version pvv "
                        "LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref "
                        "WHERE pvv.property_value_ref = $1 AND pvv.version_number = $2",
                        pv_row["id"],
                        current_v,
                    )
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "version": current_v,
                            "value": cur["value"] if cur else None,
                            "allowed_value_slug": cur["allowed_value_slug"] if cur else None,
                        },
                    )
                new_v = current_v + 1
                target_doc_ref = (
                    uuid.UUID(data.value) if prop_type == "reference" and data.value else None
                )
                await conn.execute(
                    "INSERT INTO properties_value_version "
                    "(property_value_ref, version_number, "
                    "value, allowed_value_ref, target_document_ref) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    pv_row["id"],
                    new_v,
                    data.value,
                    allowed_value_ref,
                    target_doc_ref,
                )
                await conn.execute(
                    "UPDATE properties_values SET version = $1 WHERE id = $2",
                    new_v,
                    pv_row["id"],
                )
                return_version = new_v
            await log_change(conn, wk, doc_id, "P")
            # Tout enregistrement vaut révision : reposer les auto_now du type.
            await prop_writes.apply_behaviors(conn, wk, doc_id, type_id)

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
        version=return_version,
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
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            type_id = await _get_doc_type_id(conn, wk, doc_id)
            prop_id, _, required, _, behavior = await _resolve_prop(conn, type_id, prop_slug)
            if behavior is not None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"propriété '{prop_slug}' gérée automatiquement ({behavior}) : "
                        "suppression manuelle refusée"
                    ),
                )
            if required:
                raise HTTPException(
                    status_code=422,
                    detail=f"propriété '{prop_slug}' est obligatoire (required), "
                    "impossible de supprimer sa valeur (I-4)",
                )
            deleted = await conn.fetchval(
                "DELETE FROM properties_values "
                "WHERE document_ref = $1 AND property_def_ref = $2 RETURNING id",
                doc_id,
                prop_id,
            )
            if deleted is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"aucune valeur pour la propriété '{prop_slug}' sur ce document",
                )

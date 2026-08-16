"""Synchronisation d'ensemble des documents enfants d'un parent par external_id.

Opération de haut niveau qui compose les services documentaires existants
(`create_document`, `update_document`, `set_property_value`,
`list_property_values`) pour réconcilier les enfants d'un document parent avec
une livraison d'items identifiés par une propriété `external_id`.

Idempotence : chaque item est traité indépendamment et chaque service ouvre sa
propre transaction — il n'y a PAS de transaction unique globale. L'atomicité
stricte de l'opération d'ensemble demanderait un refactor des services
documentaires (accepter une connexion en paramètre), hors périmètre. C'est un
choix assumé de réutilisation de la logique validée, pas un raccourci : chaque
écriture individuelle reste transactionnelle et l'opération est idempotente
per-item (un rejeu à l'identique n'écrit rien).
"""

from __future__ import annotations

import uuid

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.documents import service as doc_svc
from docflow.schemas.document import DocumentCreate, DocumentUpdate
from docflow.schemas.property_value import PropertyValueOut, PropertyValueSet

log = structlog.get_logger(__name__)

# Contrat du tool : slugs stables de la propriété de corrélation, du statut et
# de la valeur autorisée posée lors d'un retrait à la source.
EXTERNAL_ID_PROP = "external_id"
STATUS_PROP = "status"
REMOVED_AT_SOURCE = "removed_at_source"

_LOAD_CHILDREN = """
SELECT d.doc_technical_key, d.title, d.version,
       dv.content AS content,
       pvv.value AS external_id
FROM document d
LEFT JOIN document_version dv
    ON dv.document_ref = d.doc_technical_key AND dv.version_number = d.version
LEFT JOIN properties_defs pd
    ON pd.functional_type_ref = d.functional_type_ref AND pd.slug = $4
LEFT JOIN properties_values pv
    ON pv.document_ref = d.doc_technical_key AND pv.property_def_ref = pd.id
LEFT JOIN properties_value_version pvv
    ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
WHERE d.parent = $1 AND d.functional_type_ref = $2 AND d.workspace_technical_key = $3
"""


async def _resolve_context(
    conn: asyncpg.Connection, wk: uuid.UUID, parent_id: uuid.UUID, child_type_slug: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """Retourne (block_id du parent, id du type enfant) ; 404/422 sinon."""
    block_id: uuid.UUID | None = await conn.fetchval(
        "SELECT data_block_ref FROM document "
        "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
        parent_id,
        wk,
    )
    if block_id is None:
        raise HTTPException(status_code=404, detail=f"document parent {parent_id} introuvable")
    child_type_id: uuid.UUID | None = await conn.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        child_type_slug,
    )
    if child_type_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"type enfant '{child_type_slug}' introuvable dans ce workspace",
        )
    return block_id, child_type_id


def _item_properties(item: dict[str, object]) -> dict[str, str]:
    """Extrait les propriétés d'un item en {slug: str} ; {} si absent ou mal typé.

    Une valeur JSON `null` est filtrée (elle ne doit pas devenir la chaîne
    littérale "None") plutôt que d'être stringifiée.
    """
    raw = item.get("properties")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v is not None}


def _pv_set(prop_type: str, value: str, expected_version: int) -> PropertyValueSet:
    """Construit un PropertyValueSet selon le type de la propriété."""
    if prop_type == "restricted_list":
        return PropertyValueSet(allowed_value_slug=value, expected_version=expected_version)
    return PropertyValueSet(value=value, expected_version=expected_version)


async def _sync_properties(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, properties: dict[str, str]
) -> bool:
    """Écrit uniquement les propriétés dont la valeur diffère ; retourne True si écriture."""
    if not properties:
        return False
    current = await doc_svc.list_property_values(pool, ws_slug, doc_id)
    by_slug = {p.prop_slug: p for p in current}
    changed = False
    for slug, value in properties.items():
        p = by_slug.get(slug)
        if p is not None:
            cur = p.allowed_value_slug if p.type == "restricted_list" else p.value
            if cur == value:
                continue
            data = _pv_set(p.type, value, p.version or 0)
        else:
            # Propriété inconnue du type : set_property_value lèvera un 422 explicite.
            data = PropertyValueSet(value=value, expected_version=0)
        await doc_svc.set_property_value(pool, ws_slug, doc_id, slug, data)
        changed = True
    return changed


async def _sync_existing(
    pool: asyncpg.Pool,
    ws_slug: str,
    child: asyncpg.Record,
    item: dict[str, object],
) -> bool:
    """Met à jour titre/contenu/propriétés d'un enfant existant ; True si modifié."""
    doc_id: uuid.UUID = child["doc_technical_key"]
    fields: dict[str, object] = {}
    title = item.get("title")
    if title is not None and str(title) != child["title"]:
        fields["title"] = str(title)
    if "contenu" in item:
        contenu = item["contenu"]
        new_content = str(contenu) if contenu is not None else None
        if new_content != child["content"]:
            fields["content"] = new_content
    changed = False
    if fields:
        await doc_svc.update_document(
            pool,
            ws_slug,
            doc_id,
            DocumentUpdate(expected_version=child["version"], **fields),
        )
        changed = True
    if await _sync_properties(pool, ws_slug, doc_id, _item_properties(item)):
        changed = True
    return changed


async def _create_child(
    pool: asyncpg.Pool,
    ws_slug: str,
    block_id: uuid.UUID,
    parent_id: uuid.UUID,
    child_type_slug: str,
    external_id: str,
    item: dict[str, object],
) -> str:
    """Crée un document enfant du parent avec sa propriété external_id ; retourne l'id."""
    title = item.get("title")
    if title is None:
        raise HTTPException(status_code=422, detail="title requis pour créer l'enfant")
    contenu = item.get("contenu")
    props: dict[str, str] = {EXTERNAL_ID_PROP: external_id, **_item_properties(item)}
    doc = await doc_svc.create_document(
        pool,
        ws_slug,
        DocumentCreate(
            title=str(title),
            block_id=block_id,
            content=str(contenu) if contenu is not None else None,
            functional_type_slug=child_type_slug,
            parent_id=parent_id,
            properties=props,
        ),
    )
    return str(doc.doc_technical_key)


async def _mark_removed(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, status: PropertyValueOut | None
) -> bool:
    """Pose status=removed_at_source si nécessaire ; True si écriture effectuée."""
    if status is not None and status.allowed_value_slug == REMOVED_AT_SOURCE:
        return False
    expected = (status.version or 0) if status is not None else 0
    await doc_svc.set_property_value(
        pool,
        ws_slug,
        doc_id,
        STATUS_PROP,
        PropertyValueSet(allowed_value_slug=REMOVED_AT_SOURCE, expected_version=expected),
    )
    return True


async def sync_child_documents(
    pool: asyncpg.Pool,
    ws_slug: str,
    parent_id: uuid.UUID,
    child_type_slug: str,
    items: list[dict[str, object]],
    exhaustive: bool,
) -> dict[str, object]:
    """Synchronise les enfants d'un parent par external_id (create/update/remove).

    Voir le docstring du module pour le contrat d'idempotence (transactions par
    item, pas d'atomicité globale). JAMAIS de suppression : un retrait à la
    source pose la propriété status=removed_at_source.
    """
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        block_id, child_type_id = await _resolve_context(conn, wk, parent_id, child_type_slug)
        rows = await conn.fetch(_LOAD_CHILDREN, parent_id, child_type_id, wk, EXTERNAL_ID_PROP)

    existing = {r["external_id"]: r for r in rows if r["external_id"] is not None}

    created: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    removed_marked: list[str] = []
    errors: list[dict[str, object]] = []
    delivered: set[str] = set()

    for item in items:
        raw_ext = item.get("external_id")
        if not raw_ext or not isinstance(raw_ext, str):
            errors.append({"external_id": raw_ext, "error": "external_id requis (chaîne non vide)"})
            continue
        external_id = raw_ext
        delivered.add(external_id)
        try:
            child = existing.get(external_id)
            if child is not None:
                doc_id = str(child["doc_technical_key"])
                if await _sync_existing(pool, ws_slug, child, item):
                    updated.append(doc_id)
                else:
                    unchanged.append(doc_id)
            else:
                created.append(
                    await _create_child(
                        pool, ws_slug, block_id, parent_id, child_type_slug, external_id, item
                    )
                )
        except HTTPException as exc:
            errors.append({"external_id": external_id, "error": exc.detail})

    if exhaustive:
        for external_id, child in existing.items():
            if external_id in delivered:
                continue
            doc_id_u: uuid.UUID = child["doc_technical_key"]
            try:
                values = await doc_svc.list_property_values(pool, ws_slug, doc_id_u)
                status = next((v for v in values if v.prop_slug == STATUS_PROP), None)
                if await _mark_removed(pool, ws_slug, doc_id_u, status):
                    removed_marked.append(str(doc_id_u))
                else:
                    unchanged.append(str(doc_id_u))
            except HTTPException as exc:
                errors.append({"external_id": external_id, "error": exc.detail})

    counts = {
        "created": len(created),
        "updated": len(updated),
        "unchanged": len(unchanged),
        "removed_marked": len(removed_marked),
    }
    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "removed_marked": removed_marked,
        "errors": errors,
        "counts": counts,
    }

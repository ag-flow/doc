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

Clé de corrélation : `external_id` vient exclusivement de `item.external_id` et
n'est jamais écrite depuis `item.properties`. Une clé portée par plusieurs
enfants existants est ambiguë : elle est ignorée et reportée dans `errors`.
Aucune de ces deux situations ne fait échouer l'opération d'ensemble.
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
ORDER BY d.created_at, d.doc_technical_key
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


def _writable_properties(item: dict[str, object]) -> tuple[dict[str, str], str | None]:
    """Propriétés à écrire (clé de corrélation exclue) + external_id divergent éventuel.

    `external_id` est la clé de corrélation : elle provient exclusivement de
    `item.external_id`. Laisser `item.properties` la réécrire casserait la
    corrélation, l'item ne serait plus retrouvé au rejeu et un document serait
    recréé à chaque synchronisation.
    """
    props = _item_properties(item)
    shadow = props.pop(EXTERNAL_ID_PROP, None)
    return props, shadow


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
    properties: dict[str, str],
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
    if await _sync_properties(pool, ws_slug, doc_id, properties):
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
    properties: dict[str, str],
) -> str:
    """Crée un document enfant du parent avec sa propriété external_id ; retourne l'id."""
    title = item.get("title")
    if title is None:
        raise HTTPException(status_code=422, detail="title requis pour créer l'enfant")
    contenu = item.get("contenu")
    props: dict[str, str] = {**properties, EXTERNAL_ID_PROP: external_id}
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


def _index_children(
    rows: list[asyncpg.Record],
) -> tuple[dict[str, asyncpg.Record], dict[str, list[str]]]:
    """Indexe les enfants par external_id ; isole les clés portées par plusieurs enfants.

    Aucune unicité n'est garantie en base : indexer à l'aveugle masquerait tous
    les homonymes sauf un (jamais mis à jour, jamais marqués retirés). Les clés
    en collision sont donc sorties de l'index et signalées à l'appelant.
    """
    index: dict[str, asyncpg.Record] = {}
    ambiguous: dict[str, list[str]] = {}
    for row in rows:
        ext = row["external_id"]
        if ext is None:
            continue
        doc_id = str(row["doc_technical_key"])
        if ext in ambiguous:
            ambiguous[ext].append(doc_id)
        elif ext in index:
            ambiguous[ext] = [str(index.pop(ext)["doc_technical_key"]), doc_id]
        else:
            index[ext] = row
    return index, ambiguous


def _collision_errors(ambiguous: dict[str, list[str]]) -> list[dict[str, object]]:
    """Une erreur par external_id porté par plusieurs enfants du même parent."""
    return [
        {
            "external_id": ext,
            "error": (
                f"external_id en doublon sur {len(doc_ids)} enfants "
                f"({', '.join(doc_ids)}) : clé ignorée par la synchronisation"
            ),
        }
        for ext, doc_ids in ambiguous.items()
    ]


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

    existing, ambiguous = _index_children(rows)

    created: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    removed_marked: list[str] = []
    errors: list[dict[str, object]] = _collision_errors(ambiguous)
    delivered: set[str] = set()

    for item in items:
        raw_ext = item.get("external_id")
        if not raw_ext or not isinstance(raw_ext, str):
            errors.append({"external_id": raw_ext, "error": "external_id requis (chaîne non vide)"})
            continue
        external_id = raw_ext
        delivered.add(external_id)
        if external_id in ambiguous:
            continue
        properties, shadow = _writable_properties(item)
        if shadow is not None and shadow != external_id:
            errors.append(
                {
                    "external_id": external_id,
                    "error": (
                        f"properties.external_id ('{shadow}') ignoré : la clé de "
                        f"corrélation est item.external_id ('{external_id}')"
                    ),
                }
            )
        try:
            child = existing.get(external_id)
            if child is not None:
                doc_id = str(child["doc_technical_key"])
                if await _sync_existing(pool, ws_slug, child, item, properties):
                    updated.append(doc_id)
                else:
                    unchanged.append(doc_id)
            else:
                created.append(
                    await _create_child(
                        pool,
                        ws_slug,
                        block_id,
                        parent_id,
                        child_type_slug,
                        external_id,
                        item,
                        properties,
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

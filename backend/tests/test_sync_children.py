"""ATDD — Synchronisation des documents enfants par external_id.

Teste le service `sync_child_documents` au niveau service (appel direct avec
`db_pool`) : create / update / unchanged / removed_marked, mode exhaustif vs
non exhaustif, et idempotence stricte (rejeu à l'identique → aucune écriture).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest

from docflow.documents import service as doc_svc
from docflow.documents.sync import _item_properties, sync_child_documents
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import AllowedValueCreate, PropertiesDefCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


# ── Bug : une valeur JSON null devenait la chaîne littérale "None" ──────────


def test_item_properties_filters_out_none_values() -> None:
    """Une propriété à null dans l'item ne doit pas apparaître (ni a fortiori
    être stringifiée en 'None') — elle doit simplement être absente."""
    item = {"properties": {"assignee": None, "priority": "high"}}
    result = _item_properties(item)
    assert result == {"priority": "high"}
    assert "assignee" not in result


async def _setup(pool: asyncpg.Pool) -> dict[str, object]:
    """Type parent 'capture' + type enfant 'capture_item' (external_id text, status rl).

    Crée un bloc racine typé 'capture', un document parent, puis 3 enfants
    A/B/C (external_id a/b/c). Retourne les ids utiles.
    """
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
    )
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="capture", label="Capture"))
    await type_svc.create_type(
        pool,
        _WS,
        FunctionalTypeCreate(slug="capture_item", label="Capture Item", parent_slug="capture"),
    )
    parent_type_id: uuid.UUID = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = $2",
        wk,
        "capture",
    )
    # external_id (text) + status (restricted_list : active défaut, removed_at_source)
    await prop_svc.create_def(
        pool,
        _WS,
        "capture_item",
        PropertiesDefCreate(slug="external_id", label="External ID", type="text"),
    )
    await prop_svc.create_def(
        pool,
        _WS,
        "capture_item",
        PropertiesDefCreate(
            slug="status", label="Status", type="restricted_list", default_value="active"
        ),
    )
    await prop_svc.create_allowed_value(
        pool, _WS, "capture_item", "status", AllowedValueCreate(slug="active", label="Actif")
    )
    await prop_svc.create_allowed_value(
        pool,
        _WS,
        "capture_item",
        "status",
        AllowedValueCreate(slug="removed_at_source", label="Retiré à la source", position=1),
    )

    block_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        "captures",
        "Captures",
        parent_type_id,
        wk,
    )
    parent = await doc_svc.create_document(
        pool,
        _WS,
        DocumentCreate(title="Parent", functional_type_slug="capture", block_id=block_id),
    )

    children: dict[str, uuid.UUID] = {}
    for name, ext in [("A", "a"), ("B", "b"), ("C", "c")]:
        doc = await doc_svc.create_document(
            pool,
            _WS,
            DocumentCreate(
                title=f"Child {name}",
                functional_type_slug="capture_item",
                block_id=block_id,
                parent_id=parent.doc_technical_key,
                content=f"contenu {name}",
                properties={"external_id": ext},
            ),
        )
        children[ext] = doc.doc_technical_key

    return {"parent_id": parent.doc_technical_key, "children": children}


def _items_exhaustive() -> list[dict[str, object]]:
    return [
        {"external_id": "a", "title": "Child A", "contenu": "contenu A modifié"},
        {"external_id": "b", "title": "Child B", "contenu": "contenu B"},
        {"external_id": "d", "title": "Child D", "contenu": "contenu D"},
    ]


async def _status_of(pool: asyncpg.Pool, doc_id: uuid.UUID) -> str | None:
    values = await doc_svc.list_property_values(pool, _WS, doc_id)
    for v in values:
        if v.prop_slug == "status":
            return v.allowed_value_slug
    return None


@pytest.fixture()
async def synced(db_pool: asyncpg.Pool, test_workspace: dict) -> AsyncIterator[dict[str, object]]:
    yield await _setup(db_pool)


async def test_sync_exhaustive_create_update_unchanged_remove(
    db_pool: asyncpg.Pool, synced: dict[str, object]
) -> None:
    parent_id = synced["parent_id"]
    children = synced["children"]  # type: ignore[assignment]

    result = await sync_child_documents(
        db_pool,
        _WS,
        parent_id,  # type: ignore[arg-type]
        "capture_item",
        _items_exhaustive(),
        exhaustive=True,
    )

    id_a = str(children["a"])  # type: ignore[index]
    id_b = str(children["b"])  # type: ignore[index]
    id_c = str(children["c"])  # type: ignore[index]

    assert result["errors"] == []
    assert id_a in result["updated"]
    assert id_b in result["unchanged"]
    assert len(result["created"]) == 1
    assert id_c in result["removed_marked"]
    assert result["counts"] == {
        "created": 1,
        "updated": 1,
        "unchanged": 1,
        "removed_marked": 1,
    }

    # C n'est PAS supprimé, seulement marqué
    still_there = await db_pool.fetchval(
        "SELECT 1 FROM document WHERE doc_technical_key = $1",
        children["c"],  # type: ignore[index]
    )
    assert still_there == 1
    assert await _status_of(db_pool, children["c"]) == "removed_at_source"  # type: ignore[index]

    # D créé comme enfant du parent, type capture_item
    new_id = uuid.UUID(result["created"][0])  # type: ignore[index]
    row = await db_pool.fetchrow(
        "SELECT parent, functional_type_ref FROM document WHERE doc_technical_key = $1", new_id
    )
    assert row["parent"] == parent_id
    ext_d = None
    for v in await doc_svc.list_property_values(db_pool, _WS, new_id):
        if v.prop_slug == "external_id":
            ext_d = v.value
    assert ext_d == "d"


async def test_sync_non_exhaustive_ne_marque_pas_le_retrait(
    db_pool: asyncpg.Pool, synced: dict[str, object]
) -> None:
    parent_id = synced["parent_id"]
    children = synced["children"]  # type: ignore[assignment]

    result = await sync_child_documents(
        db_pool,
        _WS,
        parent_id,  # type: ignore[arg-type]
        "capture_item",
        _items_exhaustive(),
        exhaustive=False,
    )

    assert result["removed_marked"] == []
    # C reste 'active' (défaut), non marqué
    assert await _status_of(db_pool, children["c"]) == "active"  # type: ignore[index]


async def test_sync_idempotent_rejeu(db_pool: asyncpg.Pool, synced: dict[str, object]) -> None:
    parent_id = synced["parent_id"]

    # 1er passage exhaustif
    await sync_child_documents(
        db_pool,
        _WS,
        parent_id,
        "capture_item",
        _items_exhaustive(),
        exhaustive=True,  # type: ignore[arg-type]
    )
    # 2e passage à l'identique (D existe désormais) → aucune écriture
    result = await sync_child_documents(
        db_pool,
        _WS,
        parent_id,
        "capture_item",
        _items_exhaustive(),
        exhaustive=True,  # type: ignore[arg-type]
    )

    assert result["created"] == []
    assert result["updated"] == []
    assert result["removed_marked"] == []
    assert result["errors"] == []
    # A, B, D et C (déjà removed_at_source) tous unchanged → 4
    assert result["counts"]["unchanged"] == 4


# ── Bug : properties.external_id écrasait la clé de corrélation ─────────────


async def _external_id_of(pool: asyncpg.Pool, doc_id: uuid.UUID) -> str | None:
    for v in await doc_svc.list_property_values(pool, _WS, doc_id):
        if v.prop_slug == "external_id":
            return v.value
    return None


def _item_avec_conflit() -> dict[str, object]:
    """Item dont les properties portent un external_id divergent de la clé."""
    return {
        "external_id": "T-1",
        "title": "Tâche 1",
        "contenu": "corps",
        "properties": {"external_id": "t-1"},
    }


async def test_sync_creation_ignore_external_id_des_properties(
    db_pool: asyncpg.Pool, synced: dict[str, object]
) -> None:
    """La clé de corrélation vient de item.external_id, jamais des properties."""
    parent_id = synced["parent_id"]

    result = await sync_child_documents(
        db_pool,
        _WS,
        parent_id,  # type: ignore[arg-type]
        "capture_item",
        [_item_avec_conflit()],
        exhaustive=False,
    )

    assert len(result["created"]) == 1  # type: ignore[arg-type]
    new_id = uuid.UUID(result["created"][0])  # type: ignore[index]
    assert await _external_id_of(db_pool, new_id) == "T-1"
    # Le conflit est remonté explicitement, pas absorbé en silence.
    errs = result["errors"]
    assert len(errs) == 1  # type: ignore[arg-type]
    assert errs[0]["external_id"] == "T-1"  # type: ignore[index]
    assert "properties.external_id" in str(errs[0]["error"])  # type: ignore[index]


async def test_sync_rejeu_item_avec_conflit_ne_duplique_pas(
    db_pool: asyncpg.Pool, synced: dict[str, object]
) -> None:
    """Cœur du bug : au rejeu l'item doit être retrouvé, pas recréé."""
    parent_id = synced["parent_id"]

    first = await sync_child_documents(
        db_pool, _WS, parent_id, "capture_item", [_item_avec_conflit()], exhaustive=False
    )
    second = await sync_child_documents(
        db_pool, _WS, parent_id, "capture_item", [_item_avec_conflit()], exhaustive=False
    )

    assert second["created"] == []
    assert second["unchanged"] == first["created"]
    count = await db_pool.fetchval("SELECT count(*) FROM document WHERE parent = $1", parent_id)
    # 3 enfants de la fixture + 1 seul créé par les deux passages
    assert count == 4


async def test_sync_update_ne_reecrit_pas_external_id_via_properties(
    db_pool: asyncpg.Pool, synced: dict[str, object]
) -> None:
    """Un item existant ne peut pas muter sa clé de corrélation par properties."""
    parent_id = synced["parent_id"]
    children = synced["children"]  # type: ignore[assignment]
    doc_a: uuid.UUID = children["a"]  # type: ignore[index]

    result = await sync_child_documents(
        db_pool,
        _WS,
        parent_id,  # type: ignore[arg-type]
        "capture_item",
        [{"external_id": "a", "title": "Child A", "properties": {"external_id": "zzz"}}],
        exhaustive=False,
    )

    assert await _external_id_of(db_pool, doc_a) == "a"
    assert result["created"] == []
    assert len(result["errors"]) == 1  # type: ignore[arg-type]


# ── Bug : enfants en doublon d'external_id silencieusement masqués ──────────


async def test_sync_doublon_external_id_existant_remonte_une_erreur(
    db_pool: asyncpg.Pool, synced: dict[str, object]
) -> None:
    """Deux enfants portant le même external_id : collision signalée, pas masquée."""
    parent_id: uuid.UUID = synced["parent_id"]  # type: ignore[assignment]
    children = synced["children"]  # type: ignore[assignment]
    block_id: uuid.UUID = await db_pool.fetchval(
        "SELECT data_block_ref FROM document WHERE doc_technical_key = $1", parent_id
    )
    clone = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Child A bis",
            functional_type_slug="capture_item",
            block_id=block_id,
            parent_id=parent_id,
            content="doublon",
            properties={"external_id": "a"},
        ),
    )

    result = await sync_child_documents(
        db_pool,
        _WS,
        parent_id,
        "capture_item",
        [{"external_id": "a", "title": "Child A v2", "contenu": "modifié"}],
        exhaustive=True,
    )

    errs = [e for e in result["errors"] if e["external_id"] == "a"]  # type: ignore[union-attr,index]
    assert len(errs) == 1
    msg = str(errs[0]["error"])
    assert str(children["a"]) in msg and str(clone.doc_technical_key) in msg  # type: ignore[index]

    # Aucun des deux homonymes n'est touché ni marqué retiré : comportement déterministe.
    assert result["created"] == []
    assert result["updated"] == []
    assert await _status_of(db_pool, clone.doc_technical_key) == "active"
    assert await _status_of(db_pool, children["a"]) == "active"  # type: ignore[index]

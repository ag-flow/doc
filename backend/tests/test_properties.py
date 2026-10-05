from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import (
    AllowedValueCreate,
    AllowedValueUpdate,
    PropertiesDefCreate,
    PropertiesDefUpdate,
)
from docflow.schemas.property_value import PropertyValueSet
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _make_type(pool: asyncpg.Pool, slug: str = "epic") -> str:
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug=slug, label=slug.capitalize()))
    return slug


async def _make_prop(
    pool: asyncpg.Pool, type_slug: str, prop_slug: str, prop_type: str = "text"
) -> str:
    await prop_svc.create_def(
        pool,
        _WS,
        type_slug,
        PropertiesDefCreate(slug=prop_slug, label=prop_slug.capitalize(), type=prop_type),  # type: ignore[arg-type]
    )
    return prop_slug


async def test_create_property_def(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    prop = await prop_svc.create_def(
        db_pool, _WS, "epic", PropertiesDefCreate(slug="title", label="Title", type="text")
    )
    assert prop.slug == "title"
    assert prop.type == "text"


async def test_property_slug_unique_per_type(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_def(
            db_pool,
            _WS,
            "epic",
            PropertiesDefCreate(slug="status", label="Status2", type="text"),
        )
    assert exc.value.status_code == 409


async def test_list_property_defs(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "title")
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    defs = await prop_svc.list_defs(db_pool, _WS, "epic")
    slugs = [d.slug for d in defs]
    assert "title" in slugs and "status" in slugs


async def test_update_property_label(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "title")
    updated = await prop_svc.update_def(
        db_pool, _WS, "epic", "title", PropertiesDefUpdate(label="Title (renamed)")
    )
    assert updated.label == "Title (renamed)"


async def test_update_property_required_toggle(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """Le caractère obligatoire d'une propriété se bascule dans les deux sens."""
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "title")

    turned_on = await prop_svc.update_def(
        db_pool, _WS, "epic", "title", PropertiesDefUpdate(required=True)
    )
    assert turned_on.required is True

    turned_off = await prop_svc.update_def(
        db_pool, _WS, "epic", "title", PropertiesDefUpdate(required=False)
    )
    assert turned_off.required is False


async def test_delete_property_def(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "to-delete")
    await prop_svc.delete_def(db_pool, _WS, "epic", "to-delete")
    defs = await prop_svc.list_defs(db_pool, _WS, "epic")
    assert not any(d.slug == "to-delete" for d in defs)


async def test_allowed_value_only_on_restricted_list(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "title", "text")
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_allowed_value(
            db_pool, _WS, "epic", "title", AllowedValueCreate(slug="val", label="Val")
        )
    assert exc.value.status_code == 422


async def test_create_allowed_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    val = await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo", position=0)
    )
    assert val.slug == "todo"
    assert val.position == 0


async def test_allowed_value_slug_unique(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo")
    )
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_allowed_value(
            db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo2")
        )
    assert exc.value.status_code == 409


async def test_list_allowed_values_ordered(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="done", label="Done", position=2)
    )
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo", position=0)
    )
    values = await prop_svc.list_allowed_values(db_pool, _WS, "epic", "status")
    assert values[0].slug == "todo"
    assert values[1].slug == "done"


async def test_update_allowed_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo")
    )
    updated = await prop_svc.update_allowed_value(
        db_pool,
        _WS,
        "epic",
        "status",
        "todo",
        AllowedValueUpdate(label="À faire", color="#ff0000"),
    )
    assert updated.label == "À faire"
    assert updated.color == "#ff0000"


async def test_delete_allowed_value(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="todo", label="Todo")
    )
    await prop_svc.delete_allowed_value(db_pool, _WS, "epic", "status", "todo")
    values = await prop_svc.list_allowed_values(db_pool, _WS, "epic", "status")
    assert not any(v.slug == "todo" for v in values)


async def test_delete_allowed_value_used_reports_count(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD écran Types : le 409 annonce le nombre de documents concernés."""
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "status", "restricted_list")
    av = await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "status", AllowedValueCreate(slug="fait", label="Fait")
    )

    wk = test_workspace["workspace_technical_key"]
    async with db_pool.acquire() as conn:
        type_id = await conn.fetchval(
            "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='epic'", wk
        )
        prop_id = await conn.fetchval(
            "SELECT id FROM properties_defs WHERE functional_type_ref=$1 AND slug='status'",
            type_id,
        )
        block_id = await conn.fetchval(
            "INSERT INTO data_block (slug, label, functional_type_ref, "
            "workspace_technical_key) VALUES ('blk-409', 'B', $1, $2) RETURNING id",
            type_id,
            wk,
        )
        doc_id = await conn.fetchval(
            "INSERT INTO document (title, functional_type_ref, data_block_ref, "
            "workspace_technical_key) VALUES ('Doc', $1, $2, $3) RETURNING doc_technical_key",
            type_id,
            block_id,
            wk,
        )
        pv_id = await conn.fetchval(
            "INSERT INTO properties_values (document_ref, property_def_ref, "
            "workspace_technical_key, version) VALUES ($1, $2, $3, 1) RETURNING id",
            doc_id,
            prop_id,
            wk,
        )
        await conn.execute(
            "INSERT INTO properties_value_version (property_value_ref, version_number, "
            "allowed_value_ref) VALUES ($1, 1, $2)",
            pv_id,
            av.id,
        )

    with pytest.raises(HTTPException) as exc:
        await prop_svc.delete_allowed_value(db_pool, _WS, "epic", "status", "fait")
    assert exc.value.status_code == 409
    assert "1 document" in str(exc.value.detail)


async def test_types_rich_carries_documents_count(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _make_type(db_pool, "story")
    wk = test_workspace["workspace_technical_key"]
    async with db_pool.acquire() as conn:
        type_id = await conn.fetchval(
            "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='story'", wk
        )
        block_id = await conn.fetchval(
            "INSERT INTO data_block (slug, label, functional_type_ref, "
            "workspace_technical_key) VALUES ('blk-count', 'B', $1, $2) RETURNING id",
            type_id,
            wk,
        )
        await conn.execute(
            "INSERT INTO document (title, functional_type_ref, data_block_ref, "
            "workspace_technical_key) VALUES ('A', $1, $2, $3), ('B', $1, $2, $3)",
            type_id,
            block_id,
            wk,
        )
    rich = await type_svc.list_types_rich(db_pool, _WS)
    assert next(ty for ty in rich if ty.slug == "story").documents_count == 2


# ── Changement de TYPE d'une propriété (slug immuable, cohérence des données) ─


async def _seed_value(pool: asyncpg.Pool, prop_slug: str) -> None:
    """Pose UNE valeur de la propriété sur un document (données existantes)."""
    async with pool.acquire() as conn:
        wk = await conn.fetchval(
            "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
        )
        type_id = await conn.fetchval(
            "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'epic'",
            wk,
        )
        prop_id = await conn.fetchval(
            "SELECT id FROM properties_defs WHERE functional_type_ref = $1 AND slug = $2",
            type_id,
            prop_slug,
        )
        block_id = await conn.fetchval(
            "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
            "VALUES ('blk-type-change', 'B', $1, $2) "
            "ON CONFLICT DO NOTHING RETURNING id",
            type_id,
            wk,
        ) or await conn.fetchval(
            "SELECT id FROM data_block "
            "WHERE workspace_technical_key = $1 AND slug = 'blk-type-change'",
            wk,
        )
        doc_id = await conn.fetchval(
            "INSERT INTO document (title, functional_type_ref, data_block_ref, "
            "workspace_technical_key) VALUES ('Doc', $1, $2, $3) RETURNING doc_technical_key",
            type_id,
            block_id,
            wk,
        )
        await conn.execute(
            "INSERT INTO properties_values (document_ref, property_def_ref, "
            "workspace_technical_key, version) VALUES ($1, $2, $3, 1)",
            doc_id,
            prop_id,
            wk,
        )


async def test_type_change_free_without_data(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "champ")
    # Sans donnée : transition libre, même hors famille (text → int).
    updated = await prop_svc.update_def(
        db_pool, _WS, "epic", "champ", PropertiesDefUpdate(type="int")
    )
    assert updated.type == "int"


async def test_type_change_with_data_coherent_family(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "lien")
    await _seed_value(db_pool, "lien")
    # text → url : famille cohérente, permise malgré les données.
    assert (
        await prop_svc.update_def(db_pool, _WS, "epic", "lien", PropertiesDefUpdate(type="url"))
    ).type == "url"
    # url → restricted_list : encore la famille.
    assert (
        await prop_svc.update_def(
            db_pool, _WS, "epic", "lien", PropertiesDefUpdate(type="restricted_list")
        )
    ).type == "restricted_list"


async def test_type_change_with_data_incoherent_422(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "montant")
    await _seed_value(db_pool, "montant")
    with pytest.raises(HTTPException) as exc:
        await prop_svc.update_def(db_pool, _WS, "epic", "montant", PropertiesDefUpdate(type="int"))
    assert exc.value.status_code == 422
    assert "transitions permises" in str(exc.value.detail)


async def test_type_change_int_to_float_ok_reverse_refused(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "score", "int")
    await _seed_value(db_pool, "score")
    assert (
        await prop_svc.update_def(db_pool, _WS, "epic", "score", PropertiesDefUpdate(type="float"))
    ).type == "float"
    # float → int avec données : perte possible, refusé.
    with pytest.raises(HTTPException) as exc:
        await prop_svc.update_def(db_pool, _WS, "epic", "score", PropertiesDefUpdate(type="int"))
    assert exc.value.status_code == 422


# ── Transition vers restricted_list : les valeurs existantes deviennent le vocabulaire ─


async def _seed_documents_with_value(
    pool: asyncpg.Pool, prop_slug: str, values: list[str]
) -> list[uuid.UUID]:
    """Crée un document par valeur et y écrit `prop_slug` (versions courantes réelles)."""
    wk = await pool.fetchval("SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS)
    type_id = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'epic'", wk
    )
    block_id = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ('blk-vocab', 'B', $1, $2) RETURNING id",
        type_id,
        wk,
    )
    doc_ids: list[uuid.UUID] = []
    for i, value in enumerate(values):
        doc = await doc_svc.create_document(
            pool,
            _WS,
            DocumentCreate(title=f"Doc {i}", functional_type_slug="epic", block_id=block_id),
        )
        await doc_svc.set_property_value(
            pool,
            _WS,
            doc.doc_technical_key,
            prop_slug,
            PropertyValueSet(value=value, expected_version=0),
        )
        doc_ids.append(doc.doc_technical_key)
    return doc_ids


_COUNT_ORPHAN_TEXT_VALUES = """
SELECT count(*) FROM properties_values pv
JOIN properties_value_version v
  ON v.property_value_ref = pv.id AND v.version_number = pv.version
JOIN properties_defs pd ON pd.id = pv.property_def_ref
WHERE pd.slug = $1 AND pd.type = 'restricted_list'
  AND v.value IS NOT NULL AND v.allowed_value_ref IS NULL
"""

_COUNT_LINKED_TO = """
SELECT count(*) FROM properties_values pv
JOIN properties_value_version v
  ON v.property_value_ref = pv.id AND v.version_number = pv.version
JOIN properties_allowed_values av ON av.id = v.allowed_value_ref
WHERE av.slug = $1
"""


async def test_type_change_text_to_restricted_list_migre_les_valeurs(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """text → restricted_list : les valeurs existantes deviennent le vocabulaire (I-3).

    Scénario du ticket : 'statut' libre, 'todo' sur N documents. Après la
    transition les documents doivent rester visibles d'un filtre/tri par valeur
    autorisée — donc reliés au vocabulaire, pas laissés en texte.
    """
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "statut")
    await _seed_documents_with_value(db_pool, "statut", ["todo", "todo", "en-cours"])

    updated = await prop_svc.update_def(
        db_pool, _WS, "epic", "statut", PropertiesDefUpdate(type="restricted_list")
    )
    assert updated.type == "restricted_list"

    vocab = await prop_svc.list_allowed_values(db_pool, _WS, "epic", "statut")
    assert [v.slug for v in vocab] == ["en-cours", "todo"]
    assert [v.position for v in vocab] == [0, 1]

    assert await db_pool.fetchval(_COUNT_ORPHAN_TEXT_VALUES, "statut") == 0
    assert await db_pool.fetchval(_COUNT_LINKED_TO, "todo") == 2
    assert await db_pool.fetchval(_COUNT_LINKED_TO, "en-cours") == 1

    # Les documents migrés comptent désormais comme dépendants du vocabulaire.
    with pytest.raises(HTTPException) as exc:
        await prop_svc.delete_allowed_value(db_pool, _WS, "epic", "statut", "todo")
    assert exc.value.status_code == 409
    assert "2 document" in str(exc.value.detail)


async def test_type_change_text_to_restricted_list_valeurs_non_slugifiables_422(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Une valeur libre qui ne peut pas devenir un slug bloque la transition (atomique)."""
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "statut")
    await _seed_documents_with_value(db_pool, "statut", ["todo", "À faire demain"])

    with pytest.raises(HTTPException) as exc:
        await prop_svc.update_def(
            db_pool, _WS, "epic", "statut", PropertiesDefUpdate(type="restricted_list")
        )
    assert exc.value.status_code == 422
    assert "À faire demain" in str(exc.value.detail)

    # Rien n'a bougé : ni le type, ni le vocabulaire, ni les valeurs.
    assert (await prop_svc.get_def(db_pool, _WS, "epic", "statut")).type == "text"
    prop_id = await db_pool.fetchval(
        "SELECT pd.id FROM properties_defs pd JOIN functional_type ft "
        "ON ft.id = pd.functional_type_ref JOIN workspace w "
        "ON w.workspace_technical_key = ft.workspace_technical_key "
        "WHERE w.slug = $1 AND ft.slug = 'epic' AND pd.slug = 'statut'",
        _WS,
    )
    assert (
        await db_pool.fetchval(
            "SELECT count(*) FROM properties_allowed_values WHERE property_def_ref = $1", prop_id
        )
        == 0
    )


async def test_type_change_to_restricted_list_reutilise_le_vocabulaire_existant(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Aller-retour restricted_list → text → restricted_list : pas de doublon de vocabulaire."""
    await _make_type(db_pool)
    await _make_prop(db_pool, "epic", "statut", "restricted_list")
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "statut", AllowedValueCreate(slug="todo", label="À faire")
    )
    await prop_svc.update_def(db_pool, _WS, "epic", "statut", PropertiesDefUpdate(type="text"))
    await _seed_documents_with_value(db_pool, "statut", ["todo"])

    await prop_svc.update_def(
        db_pool, _WS, "epic", "statut", PropertiesDefUpdate(type="restricted_list")
    )
    vocab = await prop_svc.list_allowed_values(db_pool, _WS, "epic", "statut")
    assert [(v.slug, v.label) for v in vocab] == [("todo", "À faire")]
    assert await db_pool.fetchval(_COUNT_ORPHAN_TEXT_VALUES, "statut") == 0
    assert await db_pool.fetchval(_COUNT_LINKED_TO, "todo") == 1

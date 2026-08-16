"""Validation des valeurs par défaut (properties_defs.default_value).

Un défaut non validé est matérialisé tel quel sur chaque document créé : un
« abc » sur une propriété int casse ensuite tout tri/filtre du bloc (cast
``::numeric`` côté Postgres). On verrouille les deux niveaux : la définition
(create_def / update_def) et l'instanciation (instantiate_default_values).
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.documents.block_query import query_documents
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import (
    AllowedValueCreate,
    PropertiesDefCreate,
    PropertiesDefUpdate,
)
from docflow.schemas.query import QuerySpec, SortKey
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _setup_block(pool: asyncpg.Pool) -> uuid.UUID:
    """Type 'epic' + bloc 'board' typé epic. Retourne le block_id."""
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
    )
    epic_id: uuid.UUID = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'epic'", wk
    )
    block_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        "board",
        "Board",
        epic_id,
        wk,
    )
    return block_id


async def _current_value(pool: asyncpg.Pool, doc_id: uuid.UUID, prop_slug: str) -> str | None:
    value: str | None = await pool.fetchval(
        """
        SELECT pvv.value
        FROM properties_values pv
        JOIN properties_defs pd ON pd.id = pv.property_def_ref
        JOIN properties_value_version pvv
            ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
        WHERE pv.document_ref = $1 AND pd.slug = $2
        """,
        doc_id,
        prop_slug,
    )
    return value


# ── Niveau définition ─────────────────────────────────────────────────────────


async def test_create_def_rejects_int_default_not_int(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_def(
            db_pool,
            _WS,
            "epic",
            PropertiesDefCreate(slug="poids", label="Poids", type="int", default_value="abc"),
        )
    assert exc.value.status_code == 422
    assert "poids" in exc.value.detail
    # Rien n'a été créé : la transaction est refusée avant l'INSERT.
    assert await prop_svc.list_defs(db_pool, _WS, "epic") == []


async def test_create_def_rejects_date_default_not_date(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_def(
            db_pool,
            _WS,
            "epic",
            PropertiesDefCreate(
                slug="echeance", label="Échéance", type="date", default_value="15/09/2026"
            ),
        )
    assert exc.value.status_code == 422


async def test_create_def_rejects_float_default_not_float(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_def(
            db_pool,
            _WS,
            "epic",
            PropertiesDefCreate(slug="ratio", label="Ratio", type="float", default_value="abc"),
        )
    assert exc.value.status_code == 422


async def test_create_def_rejects_bool_and_url_defaults(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    with pytest.raises(HTTPException) as exc_bool:
        await prop_svc.create_def(
            db_pool,
            _WS,
            "epic",
            PropertiesDefCreate(slug="actif", label="Actif", type="bool", default_value="oui"),
        )
    assert exc_bool.value.status_code == 422
    with pytest.raises(HTTPException) as exc_url:
        await prop_svc.create_def(
            db_pool,
            _WS,
            "epic",
            PropertiesDefCreate(slug="lien", label="Lien", type="url", default_value="figma.com"),
        )
    assert exc_url.value.status_code == 422


async def test_create_def_rejects_reference_default_not_uuid(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    with pytest.raises(HTTPException) as exc:
        await prop_svc.create_def(
            db_pool,
            _WS,
            "epic",
            PropertiesDefCreate(
                slug="parent-doc", label="Parent", type="reference", default_value="pas-un-uuid"
            ),
        )
    assert exc.value.status_code == 422


async def test_create_def_accepts_null_default(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    prop = await prop_svc.create_def(
        db_pool, _WS, "epic", PropertiesDefCreate(slug="poids", label="Poids", type="int")
    )
    assert prop.default_value is None


async def test_create_def_restricted_list_default_before_allowed_values(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Non-régression : le vocabulaire est créé APRÈS la def — rien à vérifier ici."""
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    prop = await prop_svc.create_def(
        db_pool,
        _WS,
        "epic",
        PropertiesDefCreate(
            slug="statut", label="Statut", type="restricted_list", default_value="active"
        ),
    )
    assert prop.default_value == "active"


async def test_update_def_rejects_incompatible_default(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await prop_svc.create_def(
        db_pool, _WS, "epic", PropertiesDefCreate(slug="poids", label="Poids", type="int")
    )
    with pytest.raises(HTTPException) as exc:
        await prop_svc.update_def(
            db_pool, _WS, "epic", "poids", PropertiesDefUpdate(default_value="abc")
        )
    assert exc.value.status_code == 422
    kept = await prop_svc.get_def(db_pool, _WS, "epic", "poids")
    assert kept.default_value is None


async def test_update_def_type_change_rejects_now_invalid_default(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Le défaut stocké devient invalide pour le nouveau type → transition refusée."""
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await prop_svc.create_def(
        db_pool,
        _WS,
        "epic",
        PropertiesDefCreate(slug="code", label="Code", type="text", default_value="abc"),
    )
    with pytest.raises(HTTPException) as exc:
        await prop_svc.update_def(db_pool, _WS, "epic", "code", PropertiesDefUpdate(type="url"))
    assert exc.value.status_code == 422
    assert "default_value" in exc.value.detail
    kept = await prop_svc.get_def(db_pool, _WS, "epic", "code")
    assert kept.type == "text"


async def test_update_def_type_change_with_compatible_default(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """La même requête peut porter le nouveau type ET un défaut compatible."""
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await prop_svc.create_def(
        db_pool,
        _WS,
        "epic",
        PropertiesDefCreate(slug="code", label="Code", type="text", default_value="abc"),
    )
    updated = await prop_svc.update_def(
        db_pool,
        _WS,
        "epic",
        "code",
        PropertiesDefUpdate(type="url", default_value="https://example.com"),
    )
    assert updated.type == "url"
    assert updated.default_value == "https://example.com"


async def test_update_def_clearing_default_allows_type_change(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await prop_svc.create_def(
        db_pool,
        _WS,
        "epic",
        PropertiesDefCreate(slug="code", label="Code", type="text", default_value="abc"),
    )
    updated = await prop_svc.update_def(
        db_pool, _WS, "epic", "code", PropertiesDefUpdate(type="url", default_value=None)
    )
    assert updated.type == "url"
    assert updated.default_value is None


async def test_update_def_restricted_list_rejects_unknown_slug(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Le vocabulaire existe : un défaut hors vocabulaire est rejeté."""
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await prop_svc.create_def(
        db_pool,
        _WS,
        "epic",
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list"),
    )
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "statut", AllowedValueCreate(slug="todo", label="À faire")
    )
    with pytest.raises(HTTPException) as exc:
        await prop_svc.update_def(
            db_pool, _WS, "epic", "statut", PropertiesDefUpdate(default_value="inconnu")
        )
    assert exc.value.status_code == 422
    ok = await prop_svc.update_def(
        db_pool, _WS, "epic", "statut", PropertiesDefUpdate(default_value="todo")
    )
    assert ok.default_value == "todo"


async def test_update_def_label_only_ignores_stored_default(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Non-régression : un PATCH qui ne touche ni type ni défaut n'est jamais bloqué."""
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await prop_svc.create_def(
        db_pool,
        _WS,
        "epic",
        PropertiesDefCreate(
            slug="statut", label="Statut", type="restricted_list", default_value="pas-encore-creee"
        ),
    )
    updated = await prop_svc.update_def(
        db_pool, _WS, "epic", "statut", PropertiesDefUpdate(label="Statut (renommé)")
    )
    assert updated.label == "Statut (renommé)"


# ── Niveau instanciation ──────────────────────────────────────────────────────


async def test_valid_default_is_instantiated_and_sortable(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Non-régression : un défaut valide reste appliqué et le tri SQL fonctionne."""
    block_id = await _setup_block(db_pool)
    await prop_svc.create_def(
        db_pool,
        _WS,
        "epic",
        PropertiesDefCreate(slug="poids", label="Poids", type="int", default_value="42"),
    )
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Epic 00", slug="epic-00", block_id=block_id, functional_type_slug="epic"
        ),
    )
    assert await _current_value(db_pool, doc.doc_technical_key, "poids") == "42"

    page = await query_documents(
        db_pool,
        _WS,
        QuerySpec(workspace_slug=_WS, block_slug="board", sort=[SortKey(key="poids", dir="asc")]),
    )
    assert page.total == 1


async def test_legacy_invalid_default_is_skipped_not_stored(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Défaut corrompu déjà en base (historique) : ignoré, jamais matérialisé.

    Le document se crée quand même, et le bloc reste interrogeable (pas de 500
    sur le cast ::numeric d'un tri).
    """
    block_id = await _setup_block(db_pool)
    await prop_svc.create_def(
        db_pool,
        _WS,
        "epic",
        PropertiesDefCreate(slug="poids", label="Poids", type="int", default_value="42"),
    )
    # Corruption directe en base : simule une def écrite avant le durcissement.
    await db_pool.execute("UPDATE properties_defs SET default_value = 'abc' WHERE slug = 'poids'")

    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Epic 00", slug="epic-00", block_id=block_id, functional_type_slug="epic"
        ),
    )
    assert await _current_value(db_pool, doc.doc_technical_key, "poids") is None

    page = await query_documents(
        db_pool,
        _WS,
        QuerySpec(workspace_slug=_WS, block_slug="board", sort=[SortKey(key="poids", dir="asc")]),
    )
    assert page.total == 1


async def test_reference_default_sets_target_document_ref(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    block_id = await _setup_block(db_pool)
    target = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Cible", slug="cible", block_id=block_id, functional_type_slug="epic"),
    )
    await prop_svc.create_def(
        db_pool,
        _WS,
        "epic",
        PropertiesDefCreate(
            slug="jumeau",
            label="Jumeau",
            type="reference",
            default_value=str(target.doc_technical_key),
        ),
    )
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Source", slug="source", block_id=block_id, functional_type_slug="epic"
        ),
    )
    row = await db_pool.fetchrow(
        """
        SELECT pvv.value, pvv.target_document_ref
        FROM properties_values pv
        JOIN properties_defs pd ON pd.id = pv.property_def_ref
        JOIN properties_value_version pvv
            ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
        WHERE pv.document_ref = $1 AND pd.slug = 'jumeau'
        """,
        doc.doc_technical_key,
    )
    assert row is not None
    assert row["value"] == str(target.doc_technical_key)
    assert row["target_document_ref"] == target.doc_technical_key


async def test_reference_default_to_missing_document_is_skipped(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Cible inexistante : le défaut est ignoré, la création de document réussit."""
    block_id = await _setup_block(db_pool)
    await prop_svc.create_def(
        db_pool,
        _WS,
        "epic",
        PropertiesDefCreate(
            slug="jumeau", label="Jumeau", type="reference", default_value=str(uuid.uuid4())
        ),
    )
    doc = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Source", slug="source", block_id=block_id, functional_type_slug="epic"
        ),
    )
    assert await _current_value(db_pool, doc.doc_technical_key, "jumeau") is None


# ── Chemin import de template : le YAML est une entrée utilisateur comme une autre ──


async def _import_epic_with_default(
    pool: asyncpg.Pool, ws_slug: str, prop: dict[str, object]
) -> None:
    """Importe un template minimal portant une seule propriété sur le type 'epic'."""
    from docflow.templates.importer import run_import
    from docflow.templates.models import Template

    tpl = Template.model_validate(
        {
            "version": 1,
            "template": "tpl-default",
            "label": "Défauts",
            "functional_types": [{"slug": "epic", "label": "Epic", "properties": [prop]}],
        }
    )
    await run_import(pool, ws_slug, tpl)


async def test_import_template_rejects_invalid_scalar_default(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Un défaut non castable passé par un template doit être refusé, comme via l'API."""
    from docflow.templates.importer import UnresolvedTargetTypeError

    with pytest.raises(UnresolvedTargetTypeError):
        await _import_epic_with_default(
            db_pool, _WS, {"slug": "poids", "label": "Poids", "type": "int", "default": "abc"}
        )
    # Rollback complet : le type du template n'a pas été créé au passage.
    assert (
        await db_pool.fetchval(
            "SELECT 1 FROM properties_defs pd"
            " JOIN functional_type ft ON ft.id = pd.functional_type_ref"
            " WHERE pd.slug = 'poids'"
        )
        is None
    )


async def test_import_template_rejects_default_outside_allowed_values(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """restricted_list : le template porte son vocabulaire, le défaut est vérifiable."""
    from docflow.templates.importer import UnresolvedTargetTypeError

    with pytest.raises(UnresolvedTargetTypeError):
        await _import_epic_with_default(
            db_pool,
            _WS,
            {
                "slug": "statut",
                "label": "Statut",
                "type": "restricted_list",
                "default": "inconnu",
                "allowed_values": [{"slug": "todo", "label": "À faire"}],
            },
        )


async def test_import_template_accepts_valid_defaults(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Non-régression : un défaut valide (scalaire ou slug déclaré) passe toujours."""
    await _import_epic_with_default(
        db_pool, _WS, {"slug": "poids", "label": "Poids", "type": "int", "default": "42"}
    )
    assert (
        await db_pool.fetchval("SELECT default_value FROM properties_defs WHERE slug = 'poids'")
        == "42"
    )

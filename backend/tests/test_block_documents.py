"""Tests spec 23 : arbre du bloc, création deux temps, types autorisés, filtre chemin."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.documents import service as doc_svc
from docflow.documents.block_ops import list_block_documents
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreateInBlock
from docflow.schemas.properties import AllowedValueCreate, PropertiesDefCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _setup_agile_block(
    pool: asyncpg.Pool,
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """Crée la hiérarchie epic ⊃ feature ⊃ {story, atdd} et un bloc 'agile-board'.

    Retourne (block_id, {slug: type_id}).
    """
    epic = await type_svc.create_type(
        pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic")
    )
    feature = await type_svc.create_type(
        pool, _WS, FunctionalTypeCreate(slug="feature", label="Feature", parent_slug="epic")
    )
    story = await type_svc.create_type(
        pool, _WS, FunctionalTypeCreate(slug="story", label="Story", parent_slug="feature")
    )
    atdd = await type_svc.create_type(
        pool, _WS, FunctionalTypeCreate(slug="atdd", label="ATDD", parent_slug="feature")
    )
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
    )
    block_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        "agile-board", "Agile Board", epic.id, wk,
    )
    return block_id, {
        "epic": epic.id,
        "feature": feature.id,
        "story": story.id,
        "atdd": atdd.id,
    }


# ── DoD 2 : bloc 'epic', Add racine → crée un epic (implicite) ────────────────

async def test_dod2_create_root_document_implicit_type(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 2 : bloc epic, Add sans type → 1 type autorisé (epic) → création implicite."""
    block_id, _ = await _setup_agile_block(db_pool)

    # Racine : 1 seul type autorisé (epic) → pas besoin de spécifier
    doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Mon Epic"),
    )
    assert doc.functional_type_slug == "epic"
    assert doc.parent_id is None
    assert doc.data_block_ref == block_id
    assert doc.version == 1


async def test_dod2_list_block_after_creation(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 2 : après création, list_block_documents retourne le document."""
    block_id, _ = await _setup_agile_block(db_pool)
    doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Epic 1"),
    )
    docs = await doc_svc.list_block_documents(db_pool, _WS, "agile-board")
    ids = [d.doc_technical_key for d in docs]
    assert doc.doc_technical_key in ids


async def test_dod2_allowed_types_root(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 2 : allowed_types à la racine retourne [epic] (type du bloc)."""
    await _setup_agile_block(db_pool)
    types = await doc_svc.allowed_types(db_pool, _WS, "agile-board", parent_id=None)
    assert types == ["epic"]


# ── DoD 3 : sous feature, types autorisés = story|atdd ───────────────────────

async def test_dod3_allowed_types_under_feature(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 3 : allowed_types sous un doc de type feature → [story, atdd]."""
    await _setup_agile_block(db_pool)
    # Créer un epic racine
    epic_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Epic parent"),
    )
    # Créer un feature sous l'epic
    feature_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Feature 1", parent_id=epic_doc.doc_technical_key),
    )
    assert feature_doc.functional_type_slug == "feature"

    types = await doc_svc.allowed_types(
        db_pool, _WS, "agile-board", parent_id=feature_doc.doc_technical_key
    )
    assert set(types) == {"story", "atdd"}


async def test_dod3_create_without_type_under_feature_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 3 : sous feature, Add sans type → 422 (2+ choix)."""
    await _setup_agile_block(db_pool)
    epic_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Epic"),
    )
    feature_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Feature", parent_id=epic_doc.doc_technical_key),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.create_document_in_block(
            db_pool, _WS, "agile-board",
            DocumentCreateInBlock(title="Ambiguous", parent_id=feature_doc.doc_technical_key),
        )
    assert exc.value.status_code == 422


async def test_dod3_create_story_under_feature_ok(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 3 : sous feature, Add type=story → OK."""
    await _setup_agile_block(db_pool)
    epic_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Epic"),
    )
    feature_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Feature", parent_id=epic_doc.doc_technical_key),
    )
    story_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(
            title="Story 1",
            parent_id=feature_doc.doc_technical_key,
            functional_type_slug="story",
        ),
    )
    assert story_doc.functional_type_slug == "story"
    assert story_doc.parent_id == feature_doc.doc_technical_key


async def test_dod3_create_epic_under_feature_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 3 : sous feature, Add type=epic → 422 (contrainte miroir)."""
    await _setup_agile_block(db_pool)
    epic_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Epic"),
    )
    feature_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Feature", parent_id=epic_doc.doc_technical_key),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.create_document_in_block(
            db_pool, _WS, "agile-board",
            DocumentCreateInBlock(
                title="Bad Epic",
                parent_id=feature_doc.doc_technical_key,
                functional_type_slug="epic",
            ),
        )
    assert exc.value.status_code == 422


# ── DoD 4 : sous story (feuille) → 422 ───────────────────────────────────────

async def test_dod4_create_under_leaf_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 4 : sous story (feuille, 0 types autorisés) → 422."""
    await _setup_agile_block(db_pool)
    epic_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Epic"),
    )
    feature_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Feature", parent_id=epic_doc.doc_technical_key),
    )
    story_doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(
            title="Story",
            parent_id=feature_doc.doc_technical_key,
            functional_type_slug="story",
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await doc_svc.create_document_in_block(
            db_pool, _WS, "agile-board",
            DocumentCreateInBlock(title="Under Story", parent_id=story_doc.doc_technical_key),
        )
    assert exc.value.status_code == 422


# ── DoD 5 : parent d'un autre bloc → 422 ─────────────────────────────────────

async def test_dod5_parent_from_other_block_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 5 : parent appartenant à un autre bloc → 422."""
    block_id, type_ids = await _setup_agile_block(db_pool)

    # Créer un deuxième bloc dans le même workspace
    wk: uuid.UUID = await db_pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
    )
    await db_pool.execute(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4)",
        "other-agile-board", "Other Board", type_ids["epic"], wk,
    )

    # Créer un epic dans le deuxième bloc
    other_epic = await doc_svc.create_document_in_block(
        db_pool, _WS, "other-agile-board",
        DocumentCreateInBlock(title="Epic in other block"),
    )

    # Tenter d'ajouter une feature dans agile-board avec parent dans other-agile-board
    with pytest.raises(HTTPException) as exc:
        await doc_svc.create_document_in_block(
            db_pool, _WS, "agile-board",
            DocumentCreateInBlock(
                title="Feature cross-block",
                parent_id=other_epic.doc_technical_key,
            ),
        )
    assert exc.value.status_code == 422


# ── DoD 2 bis : instanciation valeurs par défaut ──────────────────────────────

async def test_dod2_default_value_instantiated(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 2 : après création, statut par défaut 'a_cadrer' est instancié dans properties_values."""
    block_id, _ = await _setup_agile_block(db_pool)

    # Ajouter une propriété statut de type restricted_list sur epic
    await prop_svc.create_def(
        db_pool, _WS, "epic",
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list"),
    )

    # Ajouter un allowed_value puis définir comme default
    from docflow.schemas.properties import PropertiesDefUpdate
    await prop_svc.create_allowed_value(
        db_pool, _WS, "epic", "statut",
        AllowedValueCreate(slug="a-cadrer", label="À cadrer", position=0),
    )
    await prop_svc.update_def(
        db_pool, _WS, "epic", "statut",
        PropertiesDefUpdate(default_value="a-cadrer"),
    )

    # Créer un document → doit instancier le statut par défaut
    doc = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="Epic avec statut"),
    )

    # Vérifier que properties_values contient le statut avec allowed_value "a-cadrer"
    row = await db_pool.fetchrow(
        """
        SELECT pav.slug
        FROM properties_values pv
        JOIN properties_value_version pvv
            ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
        JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
        JOIN properties_defs pd ON pd.id = pv.property_def_ref
        WHERE pv.document_ref = $1 AND pd.slug = 'statut'
        """,
        doc.doc_technical_key,
    )
    assert row is not None, "La valeur par défaut de statut doit être instanciée"
    assert row["slug"] == "a-cadrer"


# ── DoD 5 : filtre préservant le chemin ───────────────────────────────────────

async def test_dod5_filter_path_preserving(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 5 : filtre statut=done sur atdd → atdd + ses ancêtres (feature, epic) visibles."""
    block_id, type_ids = await _setup_agile_block(db_pool)

    # Ajouter statut sur atdd (type feuille)
    await prop_svc.create_def(
        db_pool, _WS, "atdd",
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list"),
    )
    await prop_svc.create_allowed_value(
        db_pool, _WS, "atdd", "statut",
        AllowedValueCreate(slug="done", label="Terminé", position=1),
    )
    await prop_svc.create_allowed_value(
        db_pool, _WS, "atdd", "statut",
        AllowedValueCreate(slug="in-progress", label="En cours", position=0),
    )

    # Créer l'arbre : epic ← feature ← atdd(done) + story(in-progress)
    epic = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board", DocumentCreateInBlock(title="E1"),
    )
    feature = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(title="F1", parent_id=epic.doc_technical_key),
    )
    atdd_done = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(
            title="ATDD done",
            parent_id=feature.doc_technical_key,
            functional_type_slug="atdd",
        ),
    )
    story_ip = await doc_svc.create_document_in_block(
        db_pool, _WS, "agile-board",
        DocumentCreateInBlock(
            title="Story in-progress",
            parent_id=feature.doc_technical_key,
            functional_type_slug="story",
        ),
    )

    # Poser statut=done sur atdd_done via properties_values directement
    wk: uuid.UUID = await db_pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
    )
    pd_id: uuid.UUID = await db_pool.fetchval(
        "SELECT id FROM properties_defs WHERE slug = 'statut' "
        "AND functional_type_ref = $1",
        type_ids["atdd"],
    )
    av_done_id: uuid.UUID = await db_pool.fetchval(
        "SELECT id FROM properties_allowed_values WHERE slug = 'done' "
        "AND property_def_ref = $1",
        pd_id,
    )
    pv_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO properties_values "
        "(document_ref, property_def_ref, version, workspace_technical_key) "
        "VALUES ($1, $2, 1, $3) RETURNING id",
        atdd_done.doc_technical_key, pd_id, wk,
    )
    await db_pool.execute(
        "INSERT INTO properties_value_version "
        "(property_value_ref, version_number, value, allowed_value_ref) "
        "VALUES ($1, 1, NULL, $2)",
        pv_id, av_done_id,
    )

    # Filtre statut=done → doit retourner atdd_done + feature + epic (ancêtres) mais PAS story
    filtered = await list_block_documents(
        db_pool, _WS, "agile-board",
        prop_slug="statut", allowed_value_slug="done",
    )
    filtered_ids = {d.doc_technical_key for d in filtered}

    assert atdd_done.doc_technical_key in filtered_ids, "atdd_done doit être visible"
    assert feature.doc_technical_key in filtered_ids, "feature (ancêtre) doit être visible"
    assert epic.doc_technical_key in filtered_ids, "epic (ancêtre) doit être visible"
    assert story_ip.doc_technical_key not in filtered_ids, "story (non done) doit être masquée"


async def test_dod5_filter_no_match_returns_empty(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """DoD 5 : filtre sur valeur inexistante → liste vide."""
    await _setup_agile_block(db_pool)
    filtered = await list_block_documents(
        db_pool, _WS, "agile-board",
        prop_slug="statut", allowed_value_slug="inexistant",
    )
    assert filtered == []

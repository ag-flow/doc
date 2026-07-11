"""Suite du moteur de requête (QuerySpec) : opérateurs typés, tri, projection,
type_slugs, sécurité (injection), pagination."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from docflow.documents import service as doc_svc
from docflow.documents.block_query import query_documents
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import AllowedValueCreate, PropertiesDefCreate
from docflow.schemas.query import FilterClause, QuerySpec, SortKey
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _setup(pool: asyncpg.Pool) -> uuid.UUID:
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="task", label="Task"))
    await type_svc.create_type(
        pool, _WS, FunctionalTypeCreate(slug="subtask", label="Subtask", parent_slug="task")
    )
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug=$1", _WS
    )
    task_ft: uuid.UUID = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='task'", wk
    )
    block_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO data_block (slug,label,functional_type_ref,workspace_technical_key) "
        "VALUES ('tasks','Tasks',$1,$2) RETURNING id",
        task_ft,
        wk,
    )
    await prop_svc.create_def(
        pool,
        _WS,
        "task",
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list"),
    )
    for slug, label, pos in [("todo", "À faire", 0), ("doing", "En cours", 1), ("done", "Fait", 2)]:
        await prop_svc.create_allowed_value(
            pool, _WS, "task", "statut", AllowedValueCreate(slug=slug, label=label, position=pos)
        )
    await prop_svc.create_def(
        pool, _WS, "task", PropertiesDefCreate(slug="priorite", label="Priorité", type="int")
    )
    await prop_svc.create_def(
        pool, _WS, "task", PropertiesDefCreate(slug="titre_court", label="Titre", type="text")
    )
    await prop_svc.create_def(
        pool, _WS, "task", PropertiesDefCreate(slug="echeance", label="Échéance", type="date")
    )

    rows = [
        ("t1", "T1", "todo", "1", "Alpha review", "2026-01-10"),
        ("t2", "T2", "doing", "5", "Beta report", "2026-03-15"),
        ("t3", "T3", "done", "3", "Gamma alpha", "2026-02-01"),
        ("t4", "T4", "todo", "10", "delta", "2026-05-20"),
    ]
    first_id: uuid.UUID | None = None
    for slug, title, statut, prio, titre, ech in rows:
        doc = await doc_svc.create_document(
            pool,
            _WS,
            DocumentCreate(
                title=title,
                slug=slug,
                block_id=block_id,
                functional_type_slug="task",
                properties={
                    "statut": statut,
                    "priorite": prio,
                    "titre_court": titre,
                    "echeance": ech,
                },
            ),
        )
        first_id = first_id or doc.doc_technical_key
    # Un subtask sous T1 (pour type_slugs).
    assert first_id is not None
    await doc_svc.create_document(
        pool,
        _WS,
        DocumentCreate(
            title="S1",
            slug="s1",
            block_id=block_id,
            functional_type_slug="subtask",
            parent_id=first_id,
        ),
    )
    return block_id


def _spec(**kw: object) -> QuerySpec:
    kw.setdefault("workspace_slug", _WS)
    kw.setdefault("block_slug", "tasks")
    return QuerySpec(**kw)  # type: ignore[arg-type]


async def _titles(pool: asyncpg.Pool, **kw: object) -> list[str]:
    page = await query_documents(pool, _WS, _spec(**kw))
    return [o.title for o in page.objects]


# ── Opérateurs restricted_list ────────────────────────────────────────────────


async def test_eq_and_in(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    assert set(
        await _titles(db_pool, filters=[FilterClause(prop="statut", op="eq", value="done")])
    ) == {"T3"}
    got = set(
        await _titles(
            db_pool, filters=[FilterClause(prop="statut", op="in", values=["todo", "done"])]
        )
    )
    assert got == {"T1", "T3", "T4"}


# ── Opérateurs text ───────────────────────────────────────────────────────────


async def test_text_contains_starts_with(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    assert set(
        await _titles(
            db_pool, filters=[FilterClause(prop="titre_court", op="contains", value="alpha")]
        )
    ) == {"T1", "T3"}
    assert set(
        await _titles(
            db_pool, filters=[FilterClause(prop="titre_court", op="starts_with", value="beta")]
        )
    ) == {"T2"}
    assert set(
        await _titles(db_pool, filters=[FilterClause(prop="titre_court", op="eq", value="delta")])
    ) == {"T4"}


# ── Opérateurs int ────────────────────────────────────────────────────────────


async def test_int_operators(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    assert set(
        await _titles(db_pool, filters=[FilterClause(prop="priorite", op="eq", value="5")])
    ) == {"T2"}
    assert set(
        await _titles(db_pool, filters=[FilterClause(prop="priorite", op="lt", value="5")])
    ) == {"T1", "T3"}
    assert set(
        await _titles(db_pool, filters=[FilterClause(prop="priorite", op="gt", value="5")])
    ) == {"T4"}
    assert set(
        await _titles(
            db_pool, filters=[FilterClause(prop="priorite", op="between", values=["3", "10"])]
        )
    ) == {"T2", "T3", "T4"}


# ── Opérateurs date ───────────────────────────────────────────────────────────


async def test_date_operators(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    assert set(
        await _titles(
            db_pool, filters=[FilterClause(prop="echeance", op="before", value="2026-02-15")]
        )
    ) == {"T1", "T3"}
    assert set(
        await _titles(
            db_pool, filters=[FilterClause(prop="echeance", op="after", value="2026-02-15")]
        )
    ) == {"T2", "T4"}
    assert set(
        await _titles(
            db_pool,
            filters=[
                FilterClause(prop="echeance", op="between", values=["2026-02-01", "2026-04-01"])
            ],
        )
    ) == {"T2", "T3"}


# ── Tri ───────────────────────────────────────────────────────────────────────


async def test_sort_int_and_title(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    asc = await _titles(db_pool, type_slugs=["task"], sort=[SortKey(key="priorite", dir="asc")])
    assert asc == ["T1", "T3", "T2", "T4"]  # 1,3,5,10
    desc = await _titles(db_pool, type_slugs=["task"], sort=[SortKey(key="priorite", dir="desc")])
    assert desc == ["T4", "T2", "T3", "T1"]


async def test_sort_restricted_list_by_pipeline(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Une restricted_list se trie par ordre de pipeline (position), pas alphabétique."""
    await _setup(db_pool)
    page = await query_documents(
        db_pool, _WS, _spec(type_slugs=["task"], sort=[SortKey(key="statut", dir="asc")])
    )
    positions = []
    for o in page.objects:
        st = next((p.allowed_value_slug for p in o.properties if p.prop_slug == "statut"), None)
        positions.append({"todo": 0, "doing": 1, "done": 2}[st])
    assert positions == sorted(positions)  # non-décroissant : todo < doing < done


# ── type_slugs & projection ───────────────────────────────────────────────────


async def test_type_slugs_filter(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    assert (await query_documents(db_pool, _WS, _spec(type_slugs=["task"]))).total == 4
    assert (await query_documents(db_pool, _WS, _spec(type_slugs=["subtask"]))).total == 1


async def test_projection_limits_properties(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    page = await query_documents(db_pool, _WS, _spec(type_slugs=["task"], projection=["statut"]))
    for o in page.objects:
        assert {p.prop_slug for p in o.properties} <= {"statut"}


# ── Validation & sécurité ─────────────────────────────────────────────────────


async def test_invalid_operator_for_type(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    with pytest.raises(HTTPException) as exc:
        await query_documents(
            db_pool, _WS, _spec(filters=[FilterClause(prop="priorite", op="contains", value="5")])
        )
    assert exc.value.status_code == 422
    assert "contains" in str(exc.value.detail)


async def test_unknown_property(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    with pytest.raises(HTTPException) as exc:
        await query_documents(
            db_pool, _WS, _spec(filters=[FilterClause(prop="nope", op="eq", value="x")])
        )
    assert exc.value.status_code == 422


async def test_injection_is_inert(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    await _setup(db_pool)
    payload = "'; DROP TABLE document; --"
    page = await query_documents(
        db_pool,
        _WS,
        _spec(filters=[FilterClause(prop="titre_court", op="contains", value=payload)]),
    )
    assert page.total == 0
    # La table est intacte : les 4 tasks + 1 subtask sont toujours là.
    remaining: int = await db_pool.fetchval(
        "SELECT count(*) FROM document d JOIN data_block b ON b.id=d.data_block_ref "
        "WHERE b.slug='tasks'"
    )
    assert remaining == 5


async def test_page_size_bounded_at_construction() -> None:
    with pytest.raises(ValidationError):
        QuerySpec(workspace_slug=_WS, block_slug="tasks", page_size=101)
    with pytest.raises(ValidationError):
        QuerySpec(workspace_slug=_WS, block_slug="tasks", page=0)

"""Feature L1 — tool MCP find_referencing_documents (backlinks fusionnés).

Vérifie la fusion des deux sources de références (lien de contenu markdown et
propriété de type reference), la dédup par via/prop, l'isolation workspace et
le contrôle d'accès via _call_tool.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

import asyncpg
import pytest

from docflow.documents import service as doc_svc
from docflow.mcp.server import _call_tool, configure
from docflow.mcp.session import McpSession, reset_current_session, set_current_session
from docflow.properties import service as prop_svc
from docflow.references.service import find_referencing_documents
from docflow.schemas.auth import AuthUser
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import PropertiesDefCreate
from docflow.schemas.property_value import PropertyValueSet
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc


def _json(result: list) -> object:
    return json.loads(result[0].text)


@pytest.fixture()
async def refs_ws(db_pool: asyncpg.Pool, make_block) -> AsyncIterator[dict[str, object]]:  # type: ignore[no-untyped-def]
    """Workspace 'refs-ws' : un type 'note' avec propriété reference 'rel',
    un bloc, une cible et deux sources (lien de contenu, propriété reference)."""
    configure(db_pool)
    await db_pool.execute("DELETE FROM workspace WHERE slug = 'refs-ws'")
    row = await db_pool.fetchrow(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) RETURNING workspace_technical_key",
        "refs-ws",
        "Refs WS",
    )
    assert row is not None
    wk: uuid.UUID = row["workspace_technical_key"]
    ws = "refs-ws"

    await type_svc.create_type(db_pool, ws, FunctionalTypeCreate(slug="note", label="Note"))
    await prop_svc.create_def(
        db_pool,
        ws,
        "note",
        PropertiesDefCreate(
            slug="rel",
            label="Relation",
            type="reference",
            target_functional_type_slug="note",
        ),
    )
    block_id = await make_block(ws, "note", "notes")

    target = await doc_svc.create_document(
        db_pool,
        ws,
        DocumentCreate(
            title="Cible", parent_id=None, functional_type_slug="note", block_id=block_id
        ),
    )
    # Source 1 : lien de contenu markdown vers la cible.
    src_content = await doc_svc.create_document(
        db_pool,
        ws,
        DocumentCreate(
            title="Source contenu",
            parent_id=None,
            functional_type_slug="note",
            block_id=block_id,
            content=f"[Cible](docflow://doc/{target.doc_technical_key})",
        ),
    )
    # Source 2 : propriété reference pointant la cible.
    src_prop = await doc_svc.create_document(
        db_pool,
        ws,
        DocumentCreate(
            title="Source propriété",
            parent_id=None,
            functional_type_slug="note",
            block_id=block_id,
        ),
    )
    await doc_svc.set_property_value(
        db_pool,
        ws,
        src_prop.doc_technical_key,
        "rel",
        PropertyValueSet(value=str(target.doc_technical_key), expected_version=0),
    )

    try:
        yield {
            "ws": ws,
            "wk": wk,
            "block_slug": "notes",
            "target_id": target.doc_technical_key,
            "src_content_id": src_content.doc_technical_key,
            "src_prop_id": src_prop.doc_technical_key,
        }
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = 'refs-ws'")


async def test_find_referencing_merges_both_sources(
    db_pool: asyncpg.Pool, refs_ws: dict[str, object]
) -> None:
    result = await find_referencing_documents(
        db_pool,
        str(refs_ws["ws"]),
        refs_ws["target_id"],  # type: ignore[arg-type]
    )
    assert len(result) == 2
    by_via = {r["via"]: r for r in result}
    assert set(by_via) == {"content", "property"}

    content = by_via["content"]
    assert content["source_id"] == str(refs_ws["src_content_id"])
    assert content["source_title"] == "Source contenu"
    assert content["block_slug"] == "notes"
    assert content["label"] == "Cible"

    prop = by_via["property"]
    assert prop["source_id"] == str(refs_ws["src_prop_id"])
    assert prop["source_title"] == "Source propriété"
    assert prop["block_slug"] == "notes"
    assert prop["prop_slug"] == "rel"


async def test_find_referencing_none(db_pool: asyncpg.Pool, refs_ws: dict[str, object]) -> None:
    """Une page sans backlink → liste vide (la source de contenu n'est citée par personne)."""
    result = await find_referencing_documents(
        db_pool,
        str(refs_ws["ws"]),
        refs_ws["src_content_id"],  # type: ignore[arg-type]
    )
    assert result == []


async def test_find_referencing_unknown_doc(
    db_pool: asyncpg.Pool, refs_ws: dict[str, object]
) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await find_referencing_documents(db_pool, str(refs_ws["ws"]), uuid.uuid4())
    assert exc.value.status_code == 404


async def test_find_referencing_unknown_workspace(db_pool: asyncpg.Pool) -> None:
    from fastapi import HTTPException

    configure(db_pool)
    with pytest.raises(HTTPException) as exc:
        await find_referencing_documents(db_pool, "ws-inexistant", uuid.uuid4())
    assert exc.value.status_code == 404


async def test_find_referencing_via_call_tool(
    db_pool: asyncpg.Pool, refs_ws: dict[str, object]
) -> None:
    configure(db_pool)
    data = _json(
        await _call_tool(
            "find_referencing_documents",
            {"workspace_slug": str(refs_ws["ws"]), "doc_id": str(refs_ws["target_id"])},
        )
    )
    assert isinstance(data, list)
    assert {r["via"] for r in data} == {"content", "property"}


async def test_find_referencing_invalid_uuid_via_call_tool(
    db_pool: asyncpg.Pool, refs_ws: dict[str, object]
) -> None:
    configure(db_pool)
    data = _json(
        await _call_tool(
            "find_referencing_documents",
            {"workspace_slug": str(refs_ws["ws"]), "doc_id": "pas-un-uuid"},
        )
    )
    assert data == {"error": "doc_id : UUID invalide"}


@contextmanager
def _session(user: AuthUser) -> Iterator[None]:
    token = set_current_session(McpSession(user=user))
    try:
        yield
    finally:
        reset_current_session(token)


async def test_find_referencing_access_denied(
    db_pool: asyncpg.Pool, refs_ws: dict[str, object]
) -> None:
    """Session non-admin sans accès au workspace → refus (« accès refusé »)."""
    configure(db_pool)
    row = await db_pool.fetchrow(
        "INSERT INTO app_user (email, label, is_admin, validated) "
        "VALUES ($1, $2, false, true) "
        "ON CONFLICT (email) DO UPDATE SET label = EXCLUDED.label RETURNING id",
        "refs-tiers@test.local",
        "Tiers",
    )
    assert row is not None
    user = AuthUser(
        id=row["id"],
        email="refs-tiers@test.local",
        label="Tiers",
        is_admin=False,
        validated=True,
        disabled=False,
    )
    try:
        with _session(user):
            data = _json(
                await _call_tool(
                    "find_referencing_documents",
                    {
                        "workspace_slug": str(refs_ws["ws"]),
                        "doc_id": str(refs_ws["target_id"]),
                    },
                )
            )
        assert "accès refusé" in data["error"]  # type: ignore[index,call-overload]
    finally:
        await db_pool.execute("DELETE FROM app_user WHERE email = 'refs-tiers@test.local'")

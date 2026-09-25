"""Surface MCP du type de contenu (épic MLD — F9).

Le ticket n'ajoute **aucun outil** : il étend `create_document` d'un paramètre
optionnel, expose le type dans `get_document`, et fait remonter des refus
structurés. La boucle d'un agent doit être auto-suffisante : créer avec une
grammaire, relire pour savoir laquelle, corriger sur refus.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

from docflow.mcp.server import _TOOLS, _create_document, _get_document, configure

VALID_SCHEMA = "name: client\nfields:\n  - name: id\n    type: uuid\n"
_WS = "mcp-ct-ws"
_BLOCK = "epics"


def _json(result: Any) -> Any:
    return json.loads(result[0].text)


@pytest.fixture()
async def mcp_ws(db_pool: asyncpg.Pool) -> AsyncIterator[dict[str, object]]:
    """Workspace minimal pour cette surface : un type, un bloc, un document."""
    configure(db_pool)
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", _WS)

    row = await db_pool.fetchrow(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) "
        "RETURNING workspace_technical_key",
        _WS,
        "MCP content-type WS",
    )
    assert row is not None
    wk: uuid.UUID = row["workspace_technical_key"]
    await db_pool.execute(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) VALUES ($1, $2, $3)",
        "epic",
        "Epic",
        wk,
    )

    from docflow.blocks import service as block_svc
    from docflow.schemas.block import DataBlockCreate

    await block_svc.create_block(
        db_pool, _WS, DataBlockCreate(slug=_BLOCK, label="Epics", functional_type_slug="epic")
    )
    doc = _json(
        await _create_document(
            db_pool,
            {
                "workspace_slug": _WS,
                "block_slug": _BLOCK,
                "title": "Epic A",
                "contenu": "# Epic A",
                "functional_type_slug": "epic",
            },
        )
    )
    assert doc["created"] is True
    try:
        yield {"ws_slug": _WS, "doc_id": str(doc["id"])}
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", _WS)


async def _create(db_pool: asyncpg.Pool, ws_slug: str, title: str, **extra: Any) -> Any:
    # Le type FONCTIONNEL est requis depuis T2 ; ces tests portent sur le type de
    # CONTENU, on le pose donc par défaut pour ne pas brouiller leur objet.
    args: dict[str, Any] = {
        "workspace_slug": ws_slug,
        "block_slug": _BLOCK,
        "title": title,
        "functional_type_slug": "epic",
        **extra,
    }
    return _json(await _create_document(db_pool, args))


# ── Déclaration de l'outil ───────────────────────────────────────────────────


def test_create_document_declare_le_parametre_content_type() -> None:
    tool = next(t for t in _TOOLS if t.name == "create_document")
    props = tool.inputSchema["properties"]

    assert "content_type" in props
    # Optionnel : aucun appelant existant ne doit être cassé.
    assert "content_type" not in tool.inputSchema.get("required", [])


def test_update_document_n_expose_pas_le_type_de_contenu() -> None:
    """Décision d'épic : changer la grammaire n'est pas un effet de bord d'écriture."""
    tool = next(t for t in _TOOLS if t.name == "update_document")
    assert "content_type" not in tool.inputSchema["properties"]


# ── Création ─────────────────────────────────────────────────────────────────


async def test_creation_avec_un_type_de_contenu(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    configure(db_pool)
    created = await _create(
        db_pool,
        mcp_ws["ws_slug"],  # type: ignore[arg-type]
        "Client MCP",
        contenu=VALID_SCHEMA,
        content_type="table-schema",
    )
    assert created["created"] is True

    relu = _json(await _get_document(db_pool, mcp_ws["ws_slug"], created["id"]))  # type: ignore[arg-type]
    assert relu["content_type"] == "table-schema"


async def test_creation_sans_type_reste_du_markdown(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Sans `content_type` déclaré, le corps reste du markdown."""
    configure(db_pool)
    created = await _create(
        db_pool, mcp_ws["ws_slug"], "Page MCP", contenu="# Bonjour"  # type: ignore[arg-type]
    )
    relu = _json(await _get_document(db_pool, mcp_ws["ws_slug"], created["id"]))  # type: ignore[arg-type]
    assert relu["content_type"] == "md"


# ── Lecture ──────────────────────────────────────────────────────────────────


async def test_get_document_expose_le_type_de_contenu(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Sans quoi un agent ne peut pas savoir dans quelle grammaire écrire."""
    configure(db_pool)
    data = _json(await _get_document(db_pool, mcp_ws["ws_slug"], mcp_ws["doc_id"]))  # type: ignore[arg-type]
    assert data["content_type"] == "md"


# ── Refus structurés ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("contenu", "code"),
    [
        ("name: t\n  f: [oups\n", "content_unparseable"),
        ("name: t\nfields:\n  - name: a\n    type: varchar(255)\n", "content_invalid"),
    ],
)
async def test_un_contenu_refuse_remonte_un_code_structure(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object], contenu: str, code: str
) -> None:
    configure(db_pool)
    data = await _create(
        db_pool,
        mcp_ws["ws_slug"],  # type: ignore[arg-type]
        f"Refusé {code}",
        contenu=contenu,
        content_type="table-schema",
    )

    assert "error" in data
    assert data["error_code"] == code
    assert data["error_detail"]["issues"]
    # Le pointeur vers la grammaire rend la boucle agent auto-suffisante.
    assert data["error_detail"]["doc"]


async def test_le_refus_donne_le_chemin_et_le_vocabulaire(
    db_pool: asyncpg.Pool, mcp_ws: dict[str, object]
) -> None:
    """Un agent doit pouvoir corriger sans deviner."""
    configure(db_pool)
    data = await _create(
        db_pool,
        mcp_ws["ws_slug"],  # type: ignore[arg-type]
        "Refusé détaillé",
        contenu="name: t\nfields:\n  - name: a\n    type: int\n",
        content_type="table-schema",
    )

    issue = data["error_detail"]["issues"][0]
    assert issue["path"] == "fields[0].type"
    assert issue["code"] == "physical_type"
    assert "integer" in issue["message"]
    assert "integer" in issue["allowed"]

"""Filtre par parent du moteur de requête (`QuerySpec.parent_id`).

Fichier à part de `test_block_query.py` : celui-ci est déjà près du plafond de
300 lignes, et la hiérarchie de documents exige un montage propre (type racine +
type enfant, contrainte de position DOC-04).
"""

from __future__ import annotations

import uuid

import asyncpg

from docflow.documents import service as doc_svc
from docflow.documents.block_query import query_documents
from docflow.properties import service as prop_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.properties import AllowedValueCreate, PropertiesDefCreate
from docflow.schemas.query import FilterClause, QuerySpec, SortKey
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


async def _statut_def(pool: asyncpg.Pool, type_slug: str) -> None:
    """Propriété `statut` (restricted_list todo/done) sur un type donné.

    Posée sur les DEUX types de la hiérarchie : `_resolve_prop_types` résout le
    type de données sur tout le sous-arbre du bloc, et deux définitions de même
    type de données ne rendent pas la propriété ambiguë.
    """
    await prop_svc.create_def(
        pool,
        _WS,
        type_slug,
        PropertiesDefCreate(slug="statut", label="Statut", type="restricted_list"),
    )
    for slug, label, pos in [("todo", "À faire", 0), ("done", "Done", 1)]:
        await prop_svc.create_allowed_value(
            pool, _WS, type_slug, "statut", AllowedValueCreate(slug=slug, label=label, position=pos)
        )


async def _setup_hierarchy(pool: asyncpg.Pool) -> dict[str, uuid.UUID]:
    """Deux epics racines, trois features réparties dessous.

    Arbre monté : Epic A → (Feat A1 todo, Feat A2 done) ; Epic B → (Feat B1 todo).
    Retourne les id par titre, pour viser un parent sans le relire en SQL.
    """
    await type_svc.create_type(pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await type_svc.create_type(
        pool, _WS, FunctionalTypeCreate(slug="feature", label="Feature", parent_slug="epic")
    )
    wk: uuid.UUID = await pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", _WS
    )
    epic_ft: uuid.UUID = await pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key = $1 AND slug = 'epic'", wk
    )
    block_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        "board",
        "Board",
        epic_ft,
        wk,
    )
    await _statut_def(pool, "epic")
    await _statut_def(pool, "feature")

    ids: dict[str, uuid.UUID] = {}
    for title, slug in [("Epic A", "epic-a"), ("Epic B", "epic-b")]:
        created = await doc_svc.create_document(
            pool,
            _WS,
            DocumentCreate(
                title=title,
                slug=slug,
                block_id=block_id,
                functional_type_slug="epic",
                properties={"statut": "todo"},
            ),
        )
        ids[title] = created.doc_technical_key
    for title, slug, parent, statut in [
        ("Feat A1", "feat-a1", "Epic A", "todo"),
        ("Feat A2", "feat-a2", "Epic A", "done"),
        ("Feat B1", "feat-b1", "Epic B", "todo"),
    ]:
        created = await doc_svc.create_document(
            pool,
            _WS,
            DocumentCreate(
                title=title,
                slug=slug,
                block_id=block_id,
                parent_id=ids[parent],
                functional_type_slug="feature",
                properties={"statut": statut},
            ),
        )
        ids[title] = created.doc_technical_key
    return ids


def _spec(**kw: object) -> QuerySpec:
    kw.setdefault("workspace_slug", _WS)
    kw.setdefault("block_slug", "board")
    return QuerySpec(**kw)  # type: ignore[arg-type]


async def test_query_parent_id_returns_direct_children_only(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """`parent_id` restreint aux enfants DIRECTS, et exclut les racines.

    Le tri est explicite : sans `sort`, le moteur n'ordonne que par clé technique
    (UUID), et l'ordre attendu dépendrait du hasard de la génération.
    """
    ids = await _setup_hierarchy(db_pool)

    page = await query_documents(
        db_pool, _WS, _spec(parent_id=ids["Epic A"], sort=[SortKey(key="title")])
    )

    assert page.total == 2
    assert [o.title for o in page.objects] == ["Feat A1", "Feat A2"]
    assert all(o.parent_id == str(ids["Epic A"]) for o in page.objects)


async def test_query_parent_unknown_returns_empty_page(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Un parent inexistant rend une page vide, pas une erreur."""
    await _setup_hierarchy(db_pool)

    page = await query_documents(db_pool, _WS, _spec(parent_id=uuid.uuid4()))

    assert page.total == 0
    assert page.objects == []
    assert page.has_next is False


async def test_query_parent_combines_with_filters_as_and(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """`parent_id` et un filtre de propriété se combinent en ET, pas en OU."""
    ids = await _setup_hierarchy(db_pool)

    page = await query_documents(
        db_pool,
        _WS,
        _spec(
            parent_id=ids["Epic A"],
            type_slugs=["feature"],
            filters=[FilterClause(prop="statut", op="eq", value="todo")],
        ),
    )

    # Feat B1 est aussi 'todo' mais sous un autre parent ; Feat A2 est sous le bon
    # parent mais 'done' ; les deux epics sont 'todo' mais pas du bon type. Un OU
    # sur n'importe lequel des trois axes rendrait plus d'une ligne.
    assert page.total == 1
    assert page.objects[0].title == "Feat A1"


async def test_query_parent_via_mcp_tool(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    """Le paramètre est déclaré au schéma de l'outil MCP, et il filtre réellement."""
    import json

    from docflow.mcp.server import _TOOLS, _call_tool, configure

    tool = next(t for t in _TOOLS if t.name == "query_documents")
    assert "parent_id" in tool.inputSchema["properties"]

    ids = await _setup_hierarchy(db_pool)
    configure(db_pool)
    result = await _call_tool(
        "query_documents",
        {"workspace_slug": _WS, "block_slug": "board", "parent_id": str(ids["Epic A"])},
    )
    payload = json.loads(result[0].text)

    assert payload["total"] == 2
    assert {o["title"] for o in payload["objects"]} == {"Feat A1", "Feat A2"}


async def test_query_parent_invalid_uuid_is_refused_cleanly(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    """Un `parent_id` mal formé est REFUSÉ, et ne rend surtout pas le bloc entier.

    C'est la garde contre le piège du bug `795834bf` : un filtre que l'appelant
    croit appliqué, et une page complète qui ressemble à un résultat filtré.
    """
    from mcp.types import CallToolResult

    from docflow.mcp.server import _call_tool, configure

    await _setup_hierarchy(db_pool)
    configure(db_pool)
    result = await _call_tool(
        "query_documents",
        {"workspace_slug": _WS, "block_slug": "board", "parent_id": "pas-un-uuid"},
    )

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    assert "parent_id" in result.content[0].text  # type: ignore[union-attr]


def test_rest_body_carries_parent_id() -> None:
    """Le corps REST accepte `parent_id` et le transmet au QuerySpec.

    `BlockQueryBody` porte `extra="forbid"` et le routeur fait
    `QuerySpec(..., **body.model_dump())` : un champ ajouté au spec mais oublié
    dans le corps rend un 422 sur la surface REST, sans rien casser côté MCP —
    une divergence qui ne se verrait pas autrement.
    """
    from docflow.schemas.query import BlockQueryBody

    parent = uuid.uuid4()
    body = BlockQueryBody(parent_id=parent)  # type: ignore[call-arg]
    spec = QuerySpec(workspace_slug=_WS, block_slug="board", **body.model_dump())

    assert spec.parent_id == parent

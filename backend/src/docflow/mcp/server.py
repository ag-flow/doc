from __future__ import annotations

import json
import uuid

import asyncpg
import structlog
from mcp.server import Server
from mcp.types import TextContent, Tool

log = structlog.get_logger(__name__)

# Pool injecté au démarrage par configure()
_pool: asyncpg.Pool | None = None

_TOOLS: list[Tool] = [
    Tool(
        name="list_workspaces",
        description=(
            "Retourne la liste de tous les workspaces docflow. "
            "Chaque entrée contient : slug (clé stable à passer aux autres outils), "
            "label (nom affiché), description. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="list_types",
        description=(
            "Retourne les types fonctionnels d'un workspace (ex. epic, feature, story). "
            "Chaque type a un slug stable, un label et un éventuel parent_slug "
            "(hiérarchie). "
            "Utiliser les slugs retournés pour typer un document lors de "
            "create_document. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {
                    "type": "string",
                    "description": "Slug du workspace (issu de list_workspaces)",
                },
            },
            "required": ["workspace_slug"],
        },
    ),
    Tool(
        name="list_documents",
        description=(
            "Retourne tous les documents d'un workspace (tous blocs confondus). "
            "Chaque entrée contient : id (UUID — clé à passer à get_document, "
            "update_document et set_property_value), title, "
            "functional_type_slug (peut être null). "
            "Liste non paginée : sur un grand workspace, privilégier une recherche "
            "ciblée. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
            },
            "required": ["workspace_slug"],
        },
    ),
    Tool(
        name="get_document",
        description=(
            "Lit le contenu complet d'un document : id, title, contenu (markdown "
            "brut), functional_type_slug. "
            "Retourne {error: ...} si le document n'existe pas ou n'appartient pas "
            "au workspace indiqué. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID du document (champ id de list_documents)",
                },
            },
            "required": ["workspace_slug", "doc_id"],
        },
    ),
    Tool(
        name="create_document",
        description=(
            "Crée un document et le persiste immédiatement en base de données. "
            "ÉCRITURE : le document est visible dans l'interface et via "
            "list_documents dès la réponse. "
            "Retourne l'id (UUID) et le title du document créé. "
            "functional_type_slug est optionnel ; s'il est fourni, il doit exister "
            "dans le workspace (sinon erreur). "
            "contenu est du markdown libre, optionnel."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace cible"},
                "title": {"type": "string", "description": "Titre du document (non vide)"},
                "contenu": {
                    "type": "string",
                    "description": "Corps du document en markdown (optionnel)",
                },
                "functional_type_slug": {
                    "type": "string",
                    "description": (
                        "Type fonctionnel à associer (optionnel, "
                        "doit exister dans le workspace)"
                    ),
                },
            },
            "required": ["workspace_slug", "title"],
        },
    ),
    Tool(
        name="update_document",
        description=(
            "Modifie le titre et/ou le contenu markdown d'un document existant. "
            "ÉCRITURE : mise à jour permanente, visible immédiatement dans "
            "l'interface. "
            "Au moins un des deux champs (title ou contenu) doit être fourni, "
            "sinon erreur. "
            "Ne touche pas au type fonctionnel ni aux valeurs de propriétés "
            "(utiliser set_property_value pour cela). "
            "Retourne {error: ...} si le document est introuvable dans le workspace."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID du document à modifier",
                },
                "title": {"type": "string", "description": "Nouveau titre (omis = inchangé)"},
                "contenu": {
                    "type": "string",
                    "description": "Nouveau contenu markdown (omis = inchangé)",
                },
            },
            "required": ["workspace_slug", "doc_id"],
        },
    ),
    Tool(
        name="list_property_values",
        description=(
            "Retourne toutes les propriétés du type fonctionnel du document avec "
            "leur valeur actuelle (null si non renseignée). "
            "Chaque entrée contient : prop_slug, label, type "
            "(text | int | restricted_list), value (texte brut pour text/int), "
            "allowed_value_slug + allowed_value_label (pour restricted_list). "
            "Utiliser prop_slug et allowed_value_slug avec set_property_value "
            "pour écrire une valeur. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {"type": "string", "format": "uuid", "description": "UUID du document"},
            },
            "required": ["workspace_slug", "doc_id"],
        },
    ),
    Tool(
        name="set_property_value",
        description=(
            "Écrit (crée ou remplace) la valeur d'une propriété sur un document. "
            "ÉCRITURE : upsert permanent en base, visible immédiatement dans "
            "l'interface. "
            "Règle d'exclusivité selon le type de propriété : "
            "- text ou int → fournir value (chaîne), omettre allowed_value_slug ; "
            "- restricted_list → fournir allowed_value_slug (slug de la valeur "
            "autorisée, issu de list_property_values), omettre value. "
            "Fournir les deux champs ou aucun déclenche une erreur de validation. "
            "expected_version active la concurrence optimiste : si > 0, la mise à "
            "jour échoue quand la version courante diffère (conflit concurrent). "
            "Retourne {updated: true, prop_slug} en cas de succès."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {"type": "string", "format": "uuid", "description": "UUID du document"},
                "prop_slug": {
                    "type": "string",
                    "description": "Slug de la propriété (issu de list_property_values)",
                },
                "value": {
                    "type": "string",
                    "description": "Valeur brute — pour propriétés text ou int uniquement",
                },
                "allowed_value_slug": {
                    "type": "string",
                    "description": (
                        "Slug de la valeur autorisée — "
                        "pour propriétés restricted_list uniquement"
                    ),
                },
                "expected_version": {
                    "type": "integer",
                    "description": (
                        "Version attendue pour concurrence optimiste "
                        "(0 = désactivé, défaut)"
                    ),
                    "default": 0,
                },
            },
            "required": ["workspace_slug", "doc_id", "prop_slug"],
        },
    ),
]

mcp_server = Server("docflow")


def configure(pool: asyncpg.Pool) -> None:
    global _pool
    _pool = pool


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("MCP server not configured — call configure(pool)")
    return _pool


def _text(data: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


@mcp_server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
async def _list_tools() -> list[Tool]:
    return _TOOLS


@mcp_server.call_tool()  # type: ignore[untyped-decorator]
async def _call_tool(name: str, arguments: dict[str, object]) -> list[TextContent]:
    pool = _get_pool()
    log.info("mcp_call_tool", tool=name)

    if name == "list_workspaces":
        return await _list_workspaces(pool)
    if name == "list_types":
        return await _list_types(pool, str(arguments.get("workspace_slug", "")))
    if name == "list_documents":
        return await _list_documents(pool, str(arguments.get("workspace_slug", "")))
    if name == "get_document":
        return await _get_document(
            pool,
            str(arguments.get("workspace_slug", "")),
            str(arguments.get("doc_id", "")),
        )
    if name == "create_document":
        return await _create_document(pool, arguments)
    if name == "update_document":
        return await _update_document(pool, arguments)
    if name == "list_property_values":
        return await _list_property_values(
            pool,
            str(arguments.get("workspace_slug", "")),
            str(arguments.get("doc_id", "")),
        )
    if name == "set_property_value":
        return await _set_property_value(pool, arguments)
    return _text({"error": f"outil inconnu : {name}"})


async def _list_workspaces(pool: asyncpg.Pool) -> list[TextContent]:
    rows = await pool.fetch("SELECT slug, label, description FROM workspace ORDER BY slug")
    return _text([dict(r) for r in rows])


async def _require_workspace(conn: asyncpg.Connection, ws_slug: str) -> uuid.UUID:
    wk: uuid.UUID | None = await conn.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
    )
    if wk is None:
        raise ValueError(f"workspace '{ws_slug}' introuvable")
    return wk


async def _list_types(pool: asyncpg.Pool, ws_slug: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            "SELECT slug, label FROM functional_type "
            "WHERE workspace_technical_key = $1 ORDER BY slug",
            wk,
        )
    return _text([dict(r) for r in rows])


async def _list_documents(pool: asyncpg.Pool, ws_slug: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT d.doc_technical_key::text AS id, d.title,
                   ft.slug AS functional_type_slug
            FROM document d
            LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
            WHERE d.workspace_technical_key = $1
            ORDER BY d.title
            """,
            wk,
        )
    return _text([dict(r) for r in rows])


async def _get_document(pool: asyncpg.Pool, ws_slug: str, doc_id: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            """
            SELECT d.doc_technical_key::text AS id, d.title, d.contenu,
                   ft.slug AS functional_type_slug
            FROM document d
            LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
            WHERE d.workspace_technical_key = $1
              AND d.doc_technical_key = $2
            """,
            wk,
            uuid.UUID(doc_id),
        )
    if row is None:
        return _text({"error": f"document '{doc_id}' introuvable"})
    return _text(dict(row))


async def _create_document(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    ws_slug = str(args.get("workspace_slug", ""))
    title = str(args.get("title", ""))
    contenu = str(args["contenu"]) if "contenu" in args else None
    type_slug = str(args["functional_type_slug"]) if "functional_type_slug" in args else None

    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await _require_workspace(conn, ws_slug)
            type_id: uuid.UUID | None = None
            if type_slug:
                type_id = await conn.fetchval(
                    "SELECT id FROM functional_type "
                    "WHERE workspace_technical_key = $1 AND slug = $2",
                    wk,
                    type_slug,
                )
                if type_id is None:
                    return _text({"error": f"type '{type_slug}' introuvable"})
            row = await conn.fetchrow(
                """
                INSERT INTO document (workspace_technical_key, title, contenu, functional_type_ref)
                VALUES ($1, $2, $3, $4)
                RETURNING doc_technical_key::text AS id, title
                """,
                wk,
                title,
                contenu,
                type_id,
            )
    assert row is not None
    return _text({"created": True, "id": row["id"], "title": row["title"]})


async def _update_document(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    ws_slug = str(args.get("workspace_slug", ""))
    doc_id = str(args.get("doc_id", ""))
    title = str(args["title"]) if "title" in args else None
    contenu = str(args["contenu"]) if "contenu" in args else None

    if not title and contenu is None:
        return _text({"error": "au moins title ou contenu requis"})

    cols: list[str] = []
    vals: list[object] = [uuid.UUID(doc_id)]
    idx = 2
    if title is not None:
        cols.append(f"title = ${idx}")
        vals.append(title)
        idx += 1
    if contenu is not None:
        cols.append(f"contenu = ${idx}")
        vals.append(contenu)
        idx += 1

    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await _require_workspace(conn, ws_slug)
            updated = await conn.execute(
                f"UPDATE document SET {', '.join(cols)}, updated_at = now() "
                f"WHERE doc_technical_key = $1 AND workspace_technical_key = ${idx}",
                *vals,
                wk,
            )
    if updated == "UPDATE 0":
        return _text({"error": "document introuvable"})
    return _text({"updated": True})


async def _list_property_values(pool: asyncpg.Pool, ws_slug: str, doc_id: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT pd.slug AS prop_slug, pd.label, pd.type,
                   pv.value, pav.slug AS allowed_value_slug, pav.label AS allowed_value_label
            FROM properties_defs pd
            JOIN functional_type ft ON ft.id = pd.functional_type_ref
            JOIN document d ON d.functional_type_ref = ft.id
                           AND d.workspace_technical_key = $1
                           AND d.doc_technical_key = $2
            LEFT JOIN properties_values pv ON pv.property_def_ref = pd.id
                                          AND pv.document_ref = d.doc_technical_key
            LEFT JOIN properties_allowed_values pav ON pav.id = pv.allowed_value_ref
            ORDER BY pd.slug
            """,
            wk,
            uuid.UUID(doc_id),
        )
    return _text([dict(r) for r in rows])


async def _set_property_value(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from docflow.documents import service as doc_svc
    from docflow.schemas.property_value import PropertyValueSet

    ws_slug = str(args.get("workspace_slug", ""))
    doc_id_str = str(args.get("doc_id", ""))
    prop_slug = str(args.get("prop_slug", ""))
    value = str(args["value"]) if "value" in args else None
    allowed_value_slug = str(args["allowed_value_slug"]) if "allowed_value_slug" in args else None
    expected_version = int(str(args.get("expected_version", 0)))

    data = PropertyValueSet(
        value=value, allowed_value_slug=allowed_value_slug, expected_version=expected_version
    )
    out = await doc_svc.set_property_value(pool, ws_slug, uuid.UUID(doc_id_str), prop_slug, data)
    return _text({"updated": True, "prop_slug": out.prop_slug})

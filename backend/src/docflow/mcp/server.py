from __future__ import annotations

import json
import pathlib
import uuid

import asyncpg
import structlog
from mcp.server import Server
from mcp.types import TextContent, Tool

_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent.parent.parent / "templates"

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
            "Crée un document dans un bloc et le persiste immédiatement en base. "
            "ÉCRITURE : le document est visible dans l'interface et via "
            "list_documents dès la réponse. "
            "block_slug est requis : utiliser list_blocks (REST) ou lire la réponse "
            "de create_block pour obtenir le slug. "
            "Retourne l'id (UUID) et le title du document créé. "
            "functional_type_slug est optionnel mais doit correspondre au type du bloc "
            "(doit exister dans le workspace, sinon erreur). "
            "contenu est du markdown libre, optionnel."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace cible"},
                "block_slug": {
                    "type": "string",
                    "description": "Slug du bloc qui contiendra le document (requis)",
                },
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
            "required": ["workspace_slug", "block_slug", "title"],
        },
    ),
    Tool(
        name="update_document",
        description=(
            "Modifie le titre et/ou le contenu markdown d'un document existant. "
            "ÉCRITURE : mise à jour versionnée et permanente, visible immédiatement. "
            "Au moins un des deux champs (title ou contenu) doit être fourni, "
            "sinon erreur. "
            "La mise à jour est atomique : la version courante est lue puis "
            "incrémentée dans la même transaction (concurrence optimiste transparente). "
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
        name="get_property_value",
        description=(
            "Lit la valeur actuelle d'une seule propriété d'un document. "
            "Retourne : prop_slug, label, type (text | int | restricted_list), "
            "value (texte brut pour text/int, null si vide), "
            "allowed_value_slug + allowed_value_label (pour restricted_list, null si vide). "
            "Préférer list_property_values pour lire toutes les propriétés d'un coup ; "
            "utiliser cet outil quand seule une propriété précise est nécessaire. "
            "Retourne {error: ...} si le document ou la propriété est introuvable. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "doc_id": {"type": "string", "format": "uuid", "description": "UUID du document"},
                "prop_slug": {
                    "type": "string",
                    "description": "Slug de la propriété à lire (issu de list_property_values)",
                },
            },
            "required": ["workspace_slug", "doc_id", "prop_slug"],
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
    Tool(
        name="list_templates",
        description=(
            "Retourne la liste des modèles (templates) globaux installés sur le serveur. "
            "Chaque entrée contient : template (slug stable), label, version, "
            "type_slugs (liste des types fonctionnels définis par le template). "
            "Utiliser template_slug avec import_template ou create_block pour "
            "appliquer un modèle dans un workspace. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="create_workspace",
        description=(
            "Crée un nouveau workspace docflow et le persiste immédiatement. "
            "ÉCRITURE : le workspace est visible dans l'interface dès la réponse. "
            "slug doit être unique, en minuscules, chiffres et tirets uniquement "
            "(ex. 'mon-projet-2024'). "
            "label est le nom affiché (libre). "
            "description est optionnelle. "
            "Retourne le slug, le label et le workspace_technical_key créés. "
            "Erreur 409 si le slug est déjà pris."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Identifiant unique du workspace (minuscules, tirets)",
                },
                "label": {
                    "type": "string",
                    "description": "Nom affiché du workspace",
                },
                "description": {
                    "type": "string",
                    "description": "Description optionnelle du workspace",
                },
            },
            "required": ["slug", "label"],
        },
    ),
    Tool(
        name="import_template",
        description=(
            "Importe un modèle global (issu de list_templates) dans un workspace : "
            "crée ou met à jour les types fonctionnels et leurs propriétés. "
            "ÉCRITURE : opération additive et idempotente — appeler plusieurs fois "
            "le même template sur le même workspace est sans danger. "
            "Ne supprime jamais de types existants. "
            "Retourne {applied, no_op, adds, soft_updates} : "
            "no_op=true si le workspace avait déjà la version courante du template. "
            "Erreur si workspace_slug ou template_slug est introuvable."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {
                    "type": "string",
                    "description": "Slug du workspace cible (issu de list_workspaces)",
                },
                "template_slug": {
                    "type": "string",
                    "description": "Slug du template à importer (issu de list_templates)",
                },
            },
            "required": ["workspace_slug", "template_slug"],
        },
    ),
    Tool(
        name="create_block",
        description=(
            "Crée un bloc de données dans un workspace. "
            "ÉCRITURE : le bloc est immédiatement visible dans l'interface. "
            "functional_type_slug doit exister dans le workspace ; si template_slug "
            "est fourni, le template est importé automatiquement avant la création "
            "(idempotent — sans danger si déjà importé). "
            "slug doit être unique dans le workspace (minuscules, tirets). "
            "parent_slug est optionnel : si fourni, le bloc est enfant d'un autre bloc "
            "(contrainte miroir : le type du bloc doit être enfant du type du parent). "
            "Retourne le slug, le label et l'id du bloc créé."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {
                    "type": "string",
                    "description": "Slug du workspace cible (issu de list_workspaces)",
                },
                "slug": {
                    "type": "string",
                    "description": "Identifiant unique du bloc dans le workspace",
                },
                "label": {
                    "type": "string",
                    "description": "Nom affiché du bloc",
                },
                "functional_type_slug": {
                    "type": "string",
                    "description": "Type fonctionnel du bloc (doit exister dans le workspace)",
                },
                "parent_slug": {
                    "type": "string",
                    "description": "Slug du bloc parent (optionnel — omis = bloc racine)",
                },
                "template_slug": {
                    "type": "string",
                    "description": (
                        "Slug d'un template global à importer avant la création "
                        "(optionnel — utile si le type n'est pas encore dans le workspace)"
                    ),
                },
            },
            "required": ["workspace_slug", "slug", "label", "functional_type_slug"],
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
    if name == "get_property_value":
        return await _get_property_value(
            pool,
            str(arguments.get("workspace_slug", "")),
            str(arguments.get("doc_id", "")),
            str(arguments.get("prop_slug", "")),
        )
    if name == "set_property_value":
        return await _set_property_value(pool, arguments)
    if name == "list_templates":
        return await _list_templates()
    if name == "create_workspace":
        return await _create_workspace(pool, arguments)
    if name == "import_template":
        return await _import_template(pool, arguments)
    if name == "create_block":
        return await _create_block(pool, arguments)
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
            SELECT d.doc_technical_key::text AS id, d.title,
                   dv.content AS contenu,
                   ft.slug AS functional_type_slug
            FROM document d
            LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
            LEFT JOIN document_version dv
                   ON dv.document_ref = d.doc_technical_key
                  AND dv.version_number = d.version
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
    from fastapi import HTTPException

    from docflow.documents import service as doc_svc
    from docflow.schemas.document import DocumentCreate

    ws_slug = str(args.get("workspace_slug", ""))
    block_slug = str(args.get("block_slug", ""))
    title = str(args.get("title", ""))
    contenu = str(args["contenu"]) if "contenu" in args else None
    type_slug = str(args["functional_type_slug"]) if "functional_type_slug" in args else None

    async with pool.acquire() as conn:
        block_id: uuid.UUID | None = await conn.fetchval(
            """
            SELECT db.id FROM data_block db
            JOIN workspace w ON w.workspace_technical_key = db.workspace_technical_key
            WHERE w.slug = $1 AND db.slug = $2
            """,
            ws_slug,
            block_slug,
        )
    if block_id is None:
        return _text({"error": f"bloc '{block_slug}' introuvable dans le workspace '{ws_slug}'"})

    try:
        data = DocumentCreate(
            title=title,
            block_id=block_id,
            content=contenu,
            functional_type_slug=type_slug,
        )
        doc = await doc_svc.create_document(pool, ws_slug, data)
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text(
        {"created": True, "id": str(doc.doc_technical_key), "title": doc.title}
    )


async def _update_document(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    from fastapi import HTTPException

    from docflow.documents import service as doc_svc
    from docflow.schemas.document import DocumentUpdate

    ws_slug = str(args.get("workspace_slug", ""))
    doc_id_str = str(args.get("doc_id", ""))
    title = str(args["title"]) if "title" in args else None
    contenu = str(args["contenu"]) if "contenu" in args else None

    if not title and contenu is None:
        return _text({"error": "au moins title ou contenu requis"})

    doc_id = uuid.UUID(doc_id_str)

    # Lecture de la version courante pour la concurrence optimiste transparente
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        current_version: int | None = await conn.fetchval(
            "SELECT version FROM document "
            "WHERE doc_technical_key = $1 AND workspace_technical_key = $2",
            doc_id,
            wk,
        )
    if current_version is None:
        return _text({"error": f"document '{doc_id_str}' introuvable"})

    try:
        data = DocumentUpdate(
            title=title,
            content=contenu,
            expected_version=current_version,
        )
        doc = await doc_svc.update_document(pool, ws_slug, doc_id, data)
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text({"updated": True, "title": doc.title, "version": doc.version})


async def _list_property_values(pool: asyncpg.Pool, ws_slug: str, doc_id: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            """
            SELECT pd.slug AS prop_slug, pd.label, pd.type,
                   pvv.value,
                   pav.slug AS allowed_value_slug, pav.label AS allowed_value_label
            FROM properties_defs pd
            JOIN functional_type ft ON ft.id = pd.functional_type_ref
            JOIN document d ON d.functional_type_ref = ft.id
                           AND d.workspace_technical_key = $1
                           AND d.doc_technical_key = $2
            LEFT JOIN properties_values pv ON pv.property_def_ref = pd.id
                                          AND pv.document_ref = d.doc_technical_key
            LEFT JOIN properties_value_version pvv
                   ON pvv.property_value_ref = pv.id
                  AND pvv.version_number = pv.version
            LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
            ORDER BY pd.slug
            """,
            wk,
            uuid.UUID(doc_id),
        )
    return _text([dict(r) for r in rows])


async def _get_property_value(
    pool: asyncpg.Pool, ws_slug: str, doc_id: str, prop_slug: str
) -> list[TextContent]:
    async with pool.acquire() as conn:
        wk = await _require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            """
            SELECT pd.slug AS prop_slug, pd.label, pd.type,
                   pvv.value,
                   pav.slug AS allowed_value_slug, pav.label AS allowed_value_label
            FROM properties_defs pd
            JOIN functional_type ft ON ft.id = pd.functional_type_ref
            JOIN document d ON d.functional_type_ref = ft.id
                           AND d.workspace_technical_key = $1
                           AND d.doc_technical_key = $2
            LEFT JOIN properties_values pv ON pv.property_def_ref = pd.id
                                          AND pv.document_ref = d.doc_technical_key
            LEFT JOIN properties_value_version pvv
                   ON pvv.property_value_ref = pv.id
                  AND pvv.version_number = pv.version
            LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
            WHERE pd.slug = $3
            """,
            wk,
            uuid.UUID(doc_id),
            prop_slug,
        )
    if row is None:
        return _text({"error": f"propriété '{prop_slug}' introuvable sur ce document"})
    return _text(dict(row))


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


async def _list_templates() -> list[TextContent]:
    import yaml

    from docflow.templates.inheritance import resolve
    from docflow.templates.models import Template

    result = []
    if _TEMPLATES_DIR.exists():
        for yaml_file in sorted(_TEMPLATES_DIR.glob("*.yaml")):
            try:
                with yaml_file.open() as f:
                    raw = yaml.safe_load(f)
                tpl = Template.model_validate(raw)
                resolved = resolve(tpl)
                result.append(
                    {
                        "template": tpl.template,
                        "label": tpl.label,
                        "version": tpl.version,
                        "type_slugs": [r.slug for r in resolved],
                    }
                )
            except Exception:
                log.warning("mcp_template_load_error", file=yaml_file.name, exc_info=True)
    return _text(result)


def _find_template(template_slug: str) -> object:
    """Charge un Template depuis le répertoire global ; lève ValueError si introuvable."""
    import yaml

    from docflow.templates.models import Template

    for yaml_file in _TEMPLATES_DIR.glob("*.yaml"):
        try:
            with yaml_file.open() as f:
                raw = yaml.safe_load(f)
            tpl = Template.model_validate(raw)
            if tpl.template == template_slug:
                return tpl
        except Exception:
            continue
    raise ValueError(f"template '{template_slug}' introuvable")


async def _create_workspace(
    pool: asyncpg.Pool, args: dict[str, object]
) -> list[TextContent]:
    from fastapi import HTTPException
    from pydantic import ValidationError

    from docflow.schemas.workspace import WorkspaceCreate
    from docflow.workspaces import service as ws_svc

    ws_slug = str(args.get("slug", ""))
    label = str(args.get("label", ""))
    description = str(args["description"]) if "description" in args else None

    try:
        data = WorkspaceCreate(slug=ws_slug, label=label, description=description)
        result = await ws_svc.create_workspace(pool, data, owner_id=None)
    except ValidationError as e:
        return _text({"error": e.errors(include_url=False)})
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text(
        {
            "created": True,
            "slug": result.slug,
            "label": result.label,
            "workspace_technical_key": str(result.workspace_technical_key),
        }
    )


async def _import_template(
    pool: asyncpg.Pool, args: dict[str, object]
) -> list[TextContent]:
    from docflow.templates.importer import (
        ImportConflictError,
        VersionConflictError,
        run_import,
    )

    ws_slug = str(args.get("workspace_slug", ""))
    template_slug = str(args.get("template_slug", ""))

    try:
        tpl = _find_template(template_slug)
        report = await run_import(pool, ws_slug, tpl)  # type: ignore[arg-type]
    except VersionConflictError as e:
        return _text({"error": str(e)})
    except ImportConflictError as e:
        conflicts = [{"path": i.path, "detail": i.detail} for i in e.diff.conflicts]
        return _text({"error": "conflits bloquants", "conflicts": conflicts})
    except ValueError as e:
        return _text({"error": str(e)})

    return _text(
        {
            "applied": report.applied,
            "no_op": report.no_op,
            "adds": len(report.diff.adds),
            "soft_updates": len(report.diff.soft_updates),
        }
    )


async def _create_block(
    pool: asyncpg.Pool, args: dict[str, object]
) -> list[TextContent]:
    from fastapi import HTTPException
    from pydantic import ValidationError

    from docflow.blocks import service as block_svc
    from docflow.schemas.block import DataBlockCreate
    from docflow.templates.importer import (
        ImportConflictError,
        VersionConflictError,
        run_import,
    )

    ws_slug = str(args.get("workspace_slug", ""))
    blk_slug = str(args.get("slug", ""))
    label = str(args.get("label", ""))
    type_slug = str(args.get("functional_type_slug", ""))
    parent_slug = str(args["parent_slug"]) if "parent_slug" in args else None
    template_slug = str(args["template_slug"]) if "template_slug" in args else None

    if template_slug:
        try:
            tpl = _find_template(template_slug)
            await run_import(pool, ws_slug, tpl)  # type: ignore[arg-type]
        except VersionConflictError:
            pass  # version plus ancienne déjà installée — on continue
        except (ImportConflictError, ValueError) as e:
            return _text({"error": f"import template : {e}"})

    try:
        data = DataBlockCreate(
            slug=blk_slug,
            label=label,
            functional_type_slug=type_slug,
            parent_slug=parent_slug,
        )
        result = await block_svc.create_block(pool, ws_slug, data)
    except ValidationError as e:
        return _text({"error": e.errors(include_url=False)})
    except HTTPException as e:
        return _text({"error": e.detail})

    return _text(
        {
            "created": True,
            "id": str(result.id),
            "slug": result.slug,
            "label": result.label,
            "workspace_slug": result.workspace_slug,
            "functional_type_slug": result.functional_type_slug,
        }
    )

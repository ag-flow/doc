"""Tools MCP ``dataset_*`` : CRUD datasets tabulaires + requêtage par cellule.

Miroir du style ``artifact_tools`` : schémas d'entrée (``DATASET_TOOLS``), table
d'autorisation (``DATASET_WS_TOOLS``, écriture ?), et handlers ``handle_*`` qui
parsent les arguments, appellent le service et sérialisent la réponse. L'accès
workspace (owner/membre/superadmin) est déjà porté par ``_check_user_access`` du
serveur via ``DATASET_WS_TOOLS``.
"""

from __future__ import annotations

import json
import uuid

import asyncpg
from fastapi import HTTPException
from mcp.types import TextContent, Tool

from docflow.datasets import service
from docflow.datasets.query import query_dataset
from docflow.mcp.session import acting_identity

_WS = {"type": "string", "description": "Slug du workspace"}
_DS = {"type": "string", "format": "uuid", "description": "UUID du dataset (champ id)"}

DATASET_TOOLS: list[Tool] = [
    Tool(
        name="create_dataset",
        description=(
            "Crée un dataset tabulaire (tableau requêtable) dans un workspace. "
            "ÉCRITURE. slug stable et unique dans le workspace (409 si doublon). "
            "Retourne id, slug, label."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": _WS,
                "slug": {"type": "string", "description": "Slug stable du dataset"},
                "label": {"type": "string", "description": "Nom affiché"},
            },
            "required": ["workspace_slug", "slug", "label"],
        },
    ),
    Tool(
        name="list_datasets",
        description=(
            "Liste les datasets d'un workspace : id, slug, label, column_count, "
            "row_count. Lecture seule."
        ),
        inputSchema={
            "type": "object",
            "properties": {"workspace_slug": _WS},
            "required": ["workspace_slug"],
        },
    ),
    Tool(
        name="get_dataset",
        description=(
            "Lit un dataset complet : colonnes (slug, label, type, position, "
            "required) et lignes (id + cells {col_slug: valeur affichée}). "
            "Lecture seule."
        ),
        inputSchema={
            "type": "object",
            "properties": {"workspace_slug": _WS, "dataset_id": _DS},
            "required": ["workspace_slug", "dataset_id"],
        },
    ),
    Tool(
        name="add_dataset_column",
        description=(
            "Ajoute une colonne typée à un dataset. ÉCRITURE. type ∈ text, int, "
            "float, date, bool, url. slug unique dans le dataset (409 si doublon)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": _WS,
                "dataset_id": _DS,
                "slug": {"type": "string", "description": "Slug de la colonne"},
                "label": {"type": "string", "description": "Nom affiché"},
                "type": {
                    "type": "string",
                    "enum": ["text", "int", "float", "date", "bool", "url"],
                },
                "position": {"type": "integer", "description": "Ordre (optionnel)"},
                "required": {"type": "boolean", "description": "Obligatoire (optionnel)"},
            },
            "required": ["workspace_slug", "dataset_id", "slug", "label", "type"],
        },
    ),
    Tool(
        name="update_dataset_column",
        description=(
            "Modifie une colonne (label, type, position, required). ÉCRITURE. "
            "Un changement de type RE-COERCE toutes les cellules existantes : si "
            "une valeur n'est pas convertible, le retypage est rejeté (422) sans "
            "aucune modification."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": _WS,
                "dataset_id": _DS,
                "column_slug": {"type": "string", "description": "Slug de la colonne"},
                "label": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["text", "int", "float", "date", "bool", "url"],
                },
                "position": {"type": "integer"},
                "required": {"type": "boolean"},
            },
            "required": ["workspace_slug", "dataset_id", "column_slug"],
        },
    ),
    Tool(
        name="delete_dataset_column",
        description="Supprime une colonne et ses cellules. ÉCRITURE.",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": _WS,
                "dataset_id": _DS,
                "column_slug": {"type": "string", "description": "Slug de la colonne"},
            },
            "required": ["workspace_slug", "dataset_id", "column_slug"],
        },
    ),
    Tool(
        name="add_dataset_row",
        description=(
            "Ajoute une ligne. ÉCRITURE. cells = {col_slug: valeur brute (texte)} ; "
            "colonne inconnue → 422 ; valeur non convertible dans le type → 422 ; "
            "colonnes absentes = cellule vide. Retourne row_id."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": _WS,
                "dataset_id": _DS,
                "cells": {
                    "type": "object",
                    "description": "{col_slug: valeur brute texte}",
                    "additionalProperties": {"type": "string"},
                },
                "position": {"type": "integer", "description": "Ordre (optionnel)"},
            },
            "required": ["workspace_slug", "dataset_id", "cells"],
        },
    ),
    Tool(
        name="update_dataset_row",
        description=(
            "Met à jour les cellules fournies d'une ligne (upsert par colonne). "
            "ÉCRITURE. cells = {col_slug: valeur brute} ; colonne inconnue → 422."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": _WS,
                "dataset_id": _DS,
                "row_id": {"type": "string", "format": "uuid"},
                "cells": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["workspace_slug", "dataset_id", "row_id", "cells"],
        },
    ),
    Tool(
        name="delete_dataset_row",
        description="Supprime une ligne et ses cellules. ÉCRITURE.",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": _WS,
                "dataset_id": _DS,
                "row_id": {"type": "string", "format": "uuid"},
            },
            "required": ["workspace_slug", "dataset_id", "row_id"],
        },
    ),
    Tool(
        name="query_dataset",
        description=(
            "Requête les lignes d'un dataset. Lecture seule. filters = liste de "
            "{column, op, value} combinés en ET ; op ∈ eq, neq, gt, gte, lt, lte, "
            "contains. Le filtre porte sur l'ombre typée de la colonne. sort = "
            "{column, dir}. Pagination page/page_size. Retourne {total, page, "
            "page_size, rows:[{id, cells}]}."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": _WS,
                "dataset_id": _DS,
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "op": {
                                "type": "string",
                                "enum": ["eq", "neq", "gt", "gte", "lt", "lte", "contains"],
                            },
                            "value": {},
                        },
                        "required": ["column", "op", "value"],
                    },
                },
                "sort": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string"},
                        "dir": {"type": "string", "enum": ["asc", "desc"]},
                    },
                    "required": ["column"],
                },
                "page": {"type": "integer", "minimum": 1},
                "page_size": {"type": "integer", "minimum": 1},
            },
            "required": ["workspace_slug", "dataset_id"],
        },
    ),
]

# outil → écriture ? (create/add/update/delete = True ; list/get/query = False)
DATASET_WS_TOOLS: dict[str, bool] = {
    "create_dataset": True,
    "list_datasets": False,
    "get_dataset": False,
    "add_dataset_column": True,
    "update_dataset_column": True,
    "delete_dataset_column": True,
    "add_dataset_row": True,
    "update_dataset_row": True,
    "delete_dataset_row": True,
    "query_dataset": False,
}


def _text(data: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _dataset_id(args: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(args["dataset_id"]))


def _cells(args: dict[str, object]) -> dict[str, str]:
    raw = args.get("cells")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="cells : objet {col_slug: valeur} attendu")
    return {str(k): str(v) for k, v in raw.items()}


async def handle(name: str, pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    """Dispatch + garde de conversion : toute HTTPException/UUID invalide → {error}."""
    try:
        return await _dispatch(name, pool, args)
    except HTTPException as e:
        return _text({"error": e.detail})
    except (ValueError, KeyError) as e:
        return _text({"error": f"argument invalide : {e}"})


async def _dispatch(name: str, pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    ws = str(args.get("workspace_slug", ""))
    if name == "create_dataset":
        result = await service.create_dataset(
            pool,
            ws,
            str(args.get("slug", "")),
            str(args.get("label", "")),
            acting_identity().id,
        )
        return _text(result)
    if name == "list_datasets":
        return _text(await service.list_datasets(pool, ws))
    if name == "get_dataset":
        return _text(await service.get_dataset(pool, ws, _dataset_id(args)))
    if name == "add_dataset_column":
        return _text(
            await service.add_column(
                pool,
                ws,
                _dataset_id(args),
                str(args.get("slug", "")),
                str(args.get("label", "")),
                str(args.get("type", "")),
                _opt_int(args, "position"),
                bool(args.get("required", False)),
            )
        )
    if name == "update_dataset_column":
        return _text(
            await service.update_column(
                pool,
                ws,
                _dataset_id(args),
                str(args.get("column_slug", "")),
                _opt_str(args, "label"),
                _opt_str(args, "type"),
                _opt_int(args, "position"),
                _opt_bool(args, "required"),
            )
        )
    if name == "delete_dataset_column":
        return _text(
            await service.delete_column(
                pool, ws, _dataset_id(args), str(args.get("column_slug", ""))
            )
        )
    if name == "add_dataset_row":
        return _text(
            await service.add_row(
                pool, ws, _dataset_id(args), _cells(args), _opt_int(args, "position")
            )
        )
    if name == "update_dataset_row":
        return _text(
            await service.update_row(
                pool,
                ws,
                _dataset_id(args),
                uuid.UUID(str(args["row_id"])),
                _cells(args),
            )
        )
    if name == "delete_dataset_row":
        return _text(
            await service.delete_row(pool, ws, _dataset_id(args), uuid.UUID(str(args["row_id"])))
        )
    if name == "query_dataset":
        return _text(
            await query_dataset(
                pool,
                ws,
                _dataset_id(args),
                _opt_list(args, "filters"),
                _opt_dict(args, "sort"),
                _opt_int(args, "page") or 1,
                _opt_int(args, "page_size") or 50,
            )
        )
    return _text({"error": f"outil dataset inconnu : {name}"})


def _opt_str(args: dict[str, object], key: str) -> str | None:
    return str(args[key]) if key in args and args[key] is not None else None


def _opt_int(args: dict[str, object], key: str) -> int | None:
    return int(str(args[key])) if key in args and args[key] is not None else None


def _opt_bool(args: dict[str, object], key: str) -> bool | None:
    return bool(args[key]) if key in args and args[key] is not None else None


def _opt_list(args: dict[str, object], key: str) -> list[dict[str, object]] | None:
    val = args.get(key)
    if val is None:
        return None
    if not isinstance(val, list):
        raise HTTPException(status_code=422, detail=f"{key} : liste attendue")
    return val


def _opt_dict(args: dict[str, object], key: str) -> dict[str, object] | None:
    val = args.get(key)
    if val is None:
        return None
    if not isinstance(val, dict):
        raise HTTPException(status_code=422, detail=f"{key} : objet attendu")
    return val

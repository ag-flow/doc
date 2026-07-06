"""Tools MCP artefacts : push d'image, métadonnées, lien de téléchargement signé."""

from __future__ import annotations

import base64
import binascii
import json
import uuid

import asyncpg
from fastapi import HTTPException
from mcp.types import TextContent, Tool

from docflow.artifacts import service
from docflow.artifacts.links import build_download_query
from docflow.config.settings import Settings
from docflow.mcp.session import require_identity

ARTIFACT_TOOLS: list[Tool] = [
    Tool(
        name="create_artifact",
        description=(
            "Pousse une image (binaire encodé base64) dans un workspace. "
            "ÉCRITURE : l'artefact est stocké en base, dédupliqué par empreinte "
            "sha256 — pousser deux fois le même contenu retourne le même id "
            "(deduplicated=true). "
            "Extensions autorisées : png, jpg, jpeg, gif, webp, svg. "
            "Retourne {id, url, deduplicated, sha256, size_bytes} ; url est le "
            "chemin à insérer dans le markdown d'un document "
            "(![nom](/api/workspaces/{ws}/artifacts/{id})). "
            "L'artefact doit être référencé par un document enregistré, sinon il "
            "sera purgé automatiquement après quelques heures."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace cible"},
                "filename": {
                    "type": "string",
                    "description": "Nom de fichier avec extension (ex. schema.png)",
                },
                "data_base64": {
                    "type": "string",
                    "description": "Contenu binaire du fichier encodé en base64",
                },
            },
            "required": ["workspace_slug", "filename", "data_base64"],
        },
    ),
    Tool(
        name="get_artifact",
        description=(
            "Lit les métadonnées d'un artefact : filename, extension, media_type, "
            "size_bytes, sha256, crc32, refcount (nombre de documents qui le "
            "référencent), created_at. "
            "Ne retourne PAS le binaire — utiliser get_artifact_link pour le "
            "télécharger. "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "artifact_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID de l'artefact (champ id de create_artifact)",
                },
            },
            "required": ["workspace_slug", "artifact_id"],
        },
    ),
    Tool(
        name="get_artifact_link",
        description=(
            "Émet un lien de téléchargement signé (HMAC, durée limitée) vers le "
            "binaire d'un artefact. Le lien est utilisable sans authentification "
            "jusqu'à expiration — le contrôle d'accès est appliqué maintenant, à "
            "l'émission. "
            "Retourne {url, expires_at}. Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "artifact_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID de l'artefact",
                },
            },
            "required": ["workspace_slug", "artifact_id"],
        },
    ),
]

# Périmètre workspace des tools (fusionné dans _WS_TOOLS du serveur) : écriture ?
ARTIFACT_WS_TOOLS: dict[str, bool] = {
    "create_artifact": True,
    "get_artifact": False,
    "get_artifact_link": False,
}


def _text(data: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _parse_artifact_id(raw: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


async def handle_create_artifact(
    pool: asyncpg.Pool, settings: Settings | None, args: dict[str, object]
) -> list[TextContent]:
    if settings is None:
        return _text({"error": "configuration indisponible"})
    ws_slug = str(args.get("workspace_slug", ""))
    filename = str(args.get("filename", ""))
    try:
        data = base64.b64decode(str(args.get("data_base64", "")), validate=True)
    except (binascii.Error, ValueError):
        return _text({"error": "data_base64 invalide : base64 attendu"})
    user = require_identity()
    try:
        created = await service.create_artifact(
            pool,
            ws_slug,
            filename=filename,
            data=data,
            created_by=user.id,
            max_bytes=settings.artifact_max_bytes,
        )
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(
        {
            "id": str(created.id),
            "url": created.url,
            "deduplicated": created.deduplicated,
            "filename": created.filename,
            "media_type": created.media_type,
            "size_bytes": created.size_bytes,
            "sha256": created.sha256,
        }
    )


async def handle_get_artifact(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    ws_slug = str(args.get("workspace_slug", ""))
    artifact_id = _parse_artifact_id(args.get("artifact_id", ""))
    if artifact_id is None:
        return _text({"error": "artifact_id invalide : UUID attendu"})
    try:
        meta = await service.get_artifact_meta(pool, ws_slug, artifact_id)
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(meta.model_dump(mode="json"))


async def handle_get_artifact_link(
    pool: asyncpg.Pool, settings: Settings | None, args: dict[str, object]
) -> list[TextContent]:
    if settings is None:
        return _text({"error": "configuration indisponible"})
    ws_slug = str(args.get("workspace_slug", ""))
    artifact_id = _parse_artifact_id(args.get("artifact_id", ""))
    if artifact_id is None:
        return _text({"error": "artifact_id invalide : UUID attendu"})
    try:
        # Vérifie existence + appartenance au workspace avant d'émettre le lien
        await service.get_artifact_meta(pool, ws_slug, artifact_id)
    except HTTPException as e:
        return _text({"error": e.detail})
    ttl = settings.artifact_link_ttl_seconds
    query = build_download_query(
        ws_slug, artifact_id, ttl_seconds=ttl, secret=settings.jwt_secret.reveal()
    )
    path = f"{service.artifact_url(ws_slug, artifact_id)}/download?{query}"
    base = (settings.public_base_url or "").rstrip("/")
    expires_at = int(query.split("&")[0].removeprefix("exp="))
    return _text({"url": f"{base}{path}", "expires_at": expires_at})

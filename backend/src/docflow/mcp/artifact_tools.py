"""Tools MCP artefacts : push d'image, métadonnées, lien de téléchargement signé."""

from __future__ import annotations

import base64
import binascii
import json
import uuid

import asyncpg
import httpx
from fastapi import HTTPException
from mcp.types import TextContent, Tool

from docflow.artifacts import service
from docflow.artifacts.links import build_download_query
from docflow.config.settings import Settings
from docflow.mcp.session import require_identity
from docflow.net.ssrf import SSRFError, validate_public_url

# Téléchargement d'un artefact depuis une URL (voie source_url). Le serveur va
# chercher le binaire lui-même : les octets ne transitent jamais par la sortie
# du modèle (contrairement à data_base64, borné par le budget de tokens de
# l'appelant). Sans redirection (parade SSRF, cf. net/ssrf.py).
_DOWNLOAD_TIMEOUT = 30.0


class _DownloadError(Exception):
    """Échec du téléchargement d'un artefact via source_url (message présentable)."""


async def _download_artifact_bytes(url: str, max_bytes: int) -> bytes:
    """Télécharge le binaire d'une URL publique, plafonné à ``max_bytes`` octets.

    Applique la garde SSRF avant la requête et coupe le flux dès que la taille
    dépasse la limite (pas de body arbitrairement gros en mémoire).
    """
    try:
        await validate_public_url(url)
    except SSRFError as exc:
        raise _DownloadError(f"source_url refusée : {exc}") from exc

    buffer = bytearray()
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET", url, timeout=_DOWNLOAD_TIMEOUT, follow_redirects=False
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    buffer.extend(chunk)
                    if len(buffer) > max_bytes:
                        raise _DownloadError(
                            f"source_url trop volumineuse (dépasse {max_bytes} octets)"
                        )
    except httpx.HTTPStatusError as exc:
        raise _DownloadError(f"HTTP {exc.response.status_code} sur source_url") from exc
    except httpx.RequestError as exc:
        raise _DownloadError(f"téléchargement source_url impossible : {exc}") from exc
    return bytes(buffer)


ARTIFACT_TOOLS: list[Tool] = [
    Tool(
        name="create_artifact",
        description=(
            "Pousse un fichier (image ou tout binaire) dans un workspace. "
            "Fournir le binaire par EXACTEMENT "
            "l'une de ces deux voies : `data_base64` (contenu encodé base64, inline) "
            "OU `source_url` (URL http/https publique que LE SERVEUR télécharge "
            "lui-même — à privilégier pour une grosse image, car les octets ne "
            "transitent alors pas par la conversation). "
            "ÉCRITURE : l'artefact est stocké en base, dédupliqué par empreinte "
            "sha256 — pousser deux fois le même contenu retourne le même id "
            "(deduplicated=true). "
            "Extensions autorisées : images (png, jpg, jpeg, gif, webp, svg), "
            "documents (pdf, txt, md, csv, json, docx, xlsx, pptx), audio "
            "(mp3, wav, m4a, ogg), vidéo (mp4, webm), archives (zip). Taille "
            "max bornée par la configuration de l'instance (artifact_max_bytes). "
            "Retourne {id, url, deduplicated, sha256, size_bytes}. "
            "POUR INSÉRER l'artefact dans un document, deux formes selon le "
            "type : une IMAGE s'affiche inline via `![nom](url)` (url = champ "
            "retourné) ; TOUT AUTRE FICHIER (pdf, audio, archive…) se pose en "
            "PUCE TÉLÉCHARGEABLE avec `[libellé](artifact://{id})` SEUL sur sa "
            "ligne (libellé vide = nom de fichier). "
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
                    "description": (
                        "Contenu binaire du fichier encodé en base64 (exclusif avec source_url)"
                    ),
                },
                "source_url": {
                    "type": "string",
                    "description": (
                        "URL http/https publique du binaire, téléchargé côté serveur "
                        "(exclusif avec data_base64)"
                    ),
                },
            },
            "required": ["workspace_slug", "filename"],
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
    Tool(
        name="list_artifacts",
        description=(
            "Liste paginée des artefacts d'un workspace, du plus récent au plus "
            "ancien. Retourne {items, total, limit, offset} ; chaque item porte "
            "{id, filename, media_type, size_bytes, extension, created_at, "
            "refcount} (refcount = nombre de documents qui le référencent). "
            "Ne retourne PAS le binaire (utiliser get_artifact_link). Pagination "
            "par limit (1..200, défaut 50) et offset (défaut 0). "
            "Lecture seule — aucun effet de bord."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "description": "Taille de page (1..200, défaut 50)",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Décalage de pagination (défaut 0)",
                },
            },
            "required": ["workspace_slug"],
        },
    ),
]

# Périmètre workspace des tools (fusionné dans _WS_TOOLS du serveur) : écriture ?
ARTIFACT_WS_TOOLS: dict[str, bool] = {
    "create_artifact": True,
    "get_artifact": False,
    "get_artifact_link": False,
    "list_artifacts": False,
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
    max_bytes = settings.artifact_max_bytes

    # Exactement une source : le binaire inline (data_base64) OU une URL que le
    # serveur télécharge (source_url).
    raw_b64 = args.get("data_base64")
    raw_url = args.get("source_url")
    has_b64 = raw_b64 is not None and str(raw_b64) != ""
    has_url = raw_url is not None and str(raw_url) != ""
    if has_b64 == has_url:
        return _text({"error": "fournir exactement l'un de data_base64 ou source_url"})

    if has_url:
        try:
            data = await _download_artifact_bytes(str(raw_url), max_bytes)
        except _DownloadError as e:
            return _text({"error": str(e)})
    else:
        try:
            data = base64.b64decode(str(raw_b64), validate=True)
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
            max_bytes=max_bytes,
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


def _clamp_int(raw: object, *, default: int, lo: int, hi: int) -> int:
    if not isinstance(raw, (int, str)) or isinstance(raw, bool):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


async def handle_list_artifacts(pool: asyncpg.Pool, args: dict[str, object]) -> list[TextContent]:
    ws_slug = str(args.get("workspace_slug", ""))
    limit = _clamp_int(args.get("limit"), default=50, lo=1, hi=200)
    offset = _clamp_int(args.get("offset"), default=0, lo=0, hi=2**31 - 1)
    try:
        items, total = await service.list_artifacts(pool, ws_slug, limit=limit, offset=offset)
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text({"items": items, "total": total, "limit": limit, "offset": offset})


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

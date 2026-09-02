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

from docflow.artifacts import service, uploads
from docflow.artifacts.links import build_download_query
from docflow.config.settings import Settings
from docflow.mcp.session import acting_identity, require_identity
from docflow.net.ssrf import SSRFError, validate_public_url
from docflow.schemas.artifact import ArtifactCreatedOut

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
        name="create_upload",
        description=(
            "Ouvre un UPLOAD EN DEUX TEMPS pour pousser un fichier que tu as "
            "déjà sur ton disque SANS que ses octets passent par la "
            "conversation (contrairement à data_base64) ni par une URL déjà "
            "publiée (contrairement à source_url). N'écrit AUCUN artefact : "
            "délivre seulement un ticket. "
            "Parcours : (1) create_upload(workspace_slug, filename, size_bytes, "
            "sha256) → {upload_id, upload_url, expires_at} ; (2) envoie les "
            "octets par `curl -X PUT --data-binary @fichier <upload_url>` ; "
            "(3) create_artifact(workspace_slug, upload_id) → l'artefact naît "
            "complet. "
            "size_bytes = taille exacte du fichier en octets ; sha256 = son "
            "empreinte hexadécimale (ex. `sha256sum fichier`). Le serveur "
            "recalcule l'empreinte à la réception : un octet faux fait échouer "
            "le PUT (aucun artefact corrompu). Extension et taille sont "
            "validées ici (échec rapide). Le ticket est à usage unique, lié à "
            "ce workspace et à toi, et expire vite — appelle create_artifact "
            "juste après le PUT."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace cible"},
                "filename": {
                    "type": "string",
                    "description": "Nom de fichier avec extension (ex. rapport.pdf)",
                },
                "size_bytes": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Taille exacte du fichier en octets",
                },
                "sha256": {
                    "type": "string",
                    "description": "Empreinte sha256 du fichier (64 caractères hexadécimaux)",
                },
            },
            "required": ["workspace_slug", "filename", "size_bytes", "sha256"],
        },
    ),
    Tool(
        name="create_artifact",
        description=(
            "Pousse un fichier (image ou tout binaire) dans un workspace. "
            "Fournir le binaire par EXACTEMENT "
            "l'une de ces trois voies : `data_base64` (contenu encodé base64, "
            "inline) OU `source_url` (URL http/https publique que LE SERVEUR "
            "télécharge lui-même) OU `upload_id` (ticket obtenu via create_upload "
            "après avoir PUT les octets — à privilégier pour un fichier déjà sur "
            "ton disque : les octets ne transitent pas par la conversation). "
            "Avec `upload_id`, le nom de fichier vient du ticket ; `filename` est "
            "ignoré. "
            "ÉCRITURE : l'artefact est stocké en base, dédupliqué par empreinte "
            "sha256 — pousser deux fois le même contenu retourne le même id "
            "(deduplicated=true). "
            "Extensions autorisées : registre administrable de l'instance "
            "(images, documents, audio, vidéo, archives…) — un fichier dont "
            "l'extension n'est pas enregistrée est refusé (422). Taille max "
            "bornée par la configuration de l'instance (artifact_max_bytes). "
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
                    "description": (
                        "Nom de fichier avec extension (ex. schema.png). Requis pour "
                        "data_base64 / source_url ; ignoré avec upload_id."
                    ),
                },
                "data_base64": {
                    "type": "string",
                    "description": (
                        "Contenu binaire du fichier encodé en base64 "
                        "(exclusif avec source_url et upload_id)"
                    ),
                },
                "source_url": {
                    "type": "string",
                    "description": (
                        "URL http/https publique du binaire, téléchargé côté serveur "
                        "(exclusif avec data_base64 et upload_id)"
                    ),
                },
                "upload_id": {
                    "type": "string",
                    "description": (
                        "Ticket d'upload (create_upload) dont les octets ont déjà été "
                        "PUT (exclusif avec data_base64 et source_url)"
                    ),
                },
            },
            "required": ["workspace_slug"],
        },
    ),
    Tool(
        name="get_artifact",
        description=(
            "Lit les métadonnées d'un artefact : filename, extension, media_type, "
            "size_bytes, sha256, crc32, refcount (nombre de documents qui le "
            "référencent), created_at. "
            "Ne retourne PAS le binaire — utiliser get_artifact_data pour lire le "
            "contenu inline (petit fichier texte), ou get_artifact_link pour un "
            "lien de téléchargement (gros binaire). "
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
        name="get_artifact_data",
        description=(
            "Retourne le CONTENU d'un artefact DIRECTEMENT dans la réponse (aucun "
            "lien HTTP à suivre séparément) — pour un agent sans accès réseau "
            "sortant qui doit lire un fichier texte (.vtt, .md, .txt, .csv, .json…). "
            "Contenu texte (media_type text/*, application/json, *+xml/+json) → "
            "champ content en clair, encoding='utf-8' ; sinon → content encodé en "
            "base64, encoding='base64'. Réponse : {content, encoding, media_type, "
            "size_bytes, filename, truncated:false}. "
            "Si l'artefact dépasse la limite inline (artifact_inline_max_bytes, "
            "~1 Mio) : retourne {too_large:true, size_bytes, max_inline_bytes, "
            "media_type, hint} SANS le contenu — utiliser get_artifact_link pour "
            "un gros binaire (PDF, vidéo…). Lecture seule — aucun effet de bord."
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
        name="get_artifact_link",
        description=(
            "Émet un lien de téléchargement signé (HMAC, durée limitée) vers le "
            "binaire d'un artefact. Le lien est utilisable sans authentification "
            "jusqu'à expiration — le contrôle d'accès est appliqué maintenant, à "
            "l'émission. "
            "Retourne {url, expires_at}. Pour LIRE le contenu d'un petit fichier "
            "texte sans suivre de lien (agent sans réseau), préférer "
            "get_artifact_data. Lecture seule — aucun effet de bord."
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
            "toutes les colonnes de la table (sauf le binaire) : {id, filename, "
            "extension, media_type, size_bytes, sha256, crc32, created_by, "
            "created_at} + refcount (nombre de documents qui le référencent). "
            "sha256 = empreinte de déduplication ; created_by = id de l'auteur "
            "(null si inconnu). Ne retourne PAS le binaire (utiliser "
            "get_artifact_link). Pagination par limit (1..200, défaut 50) et "
            "offset (défaut 0). Filtres optionnels combinables : filename "
            "(correspondance partielle, insensible à la casse), sha256 "
            "(empreinte exacte — permet de retrouver un artefact par contenu), "
            "document_id (artefacts référencés par ce document). Lecture seule."
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
                "filename": {
                    "type": "string",
                    "description": "Filtre nom partiel (insensible à la casse)",
                },
                "sha256": {
                    "type": "string",
                    "description": "Filtre empreinte sha256 exacte (64 hex)",
                },
                "document_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Filtre : artefacts référencés par ce document",
                },
            },
            "required": ["workspace_slug"],
        },
    ),
]

# Périmètre workspace des tools (fusionné dans _WS_TOOLS du serveur) : écriture ?
ARTIFACT_WS_TOOLS: dict[str, bool] = {
    "create_upload": True,
    "create_artifact": True,
    "get_artifact": False,
    "get_artifact_data": False,
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


def _upload_url(settings: Settings, upload_id: str) -> str:
    """URL absolue de dépôt PUT (préfixée par public_base_url si configurée)."""
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/api/uploads/{upload_id}"


async def handle_create_upload(
    pool: asyncpg.Pool, settings: Settings | None, args: dict[str, object]
) -> list[TextContent]:
    """Ouvre un ticket d'upload : ne crée aucun artefact, retourne l'upload_url."""
    if settings is None:
        return _text({"error": "configuration indisponible"})
    ws_slug = str(args.get("workspace_slug", ""))
    filename = str(args.get("filename", ""))
    raw_size = args.get("size_bytes")
    if not isinstance(raw_size, int) or isinstance(raw_size, bool):
        return _text({"error": "size_bytes invalide : entier attendu"})
    sha256 = str(args.get("sha256", ""))

    # Le ticket est lié au PORTEUR de la clé (require_identity) : seul lui
    # pourra le consommer. L'acteur OBO, forgeable, ne sert pas de liaison.
    try:
        result = await uploads.create_upload(
            pool,
            ws_slug,
            filename=filename,
            size_bytes=raw_size,
            sha256=sha256,
            requested_by=require_identity().id,
            ttl_seconds=settings.artifact_upload_ttl_seconds,
            max_bytes=settings.artifact_max_bytes,
        )
    except HTTPException as e:
        return _text({"error": e.detail})
    upload_id = str(result["upload_id"])
    return _text(
        {
            "upload_id": upload_id,
            "upload_url": _upload_url(settings, upload_id),
            "expires_at": result["expires_at"],
        }
    )


async def handle_create_artifact(
    pool: asyncpg.Pool, settings: Settings | None, args: dict[str, object]
) -> list[TextContent]:
    if settings is None:
        return _text({"error": "configuration indisponible"})
    ws_slug = str(args.get("workspace_slug", ""))
    filename = str(args.get("filename", ""))
    max_bytes = settings.artifact_max_bytes

    # Exactement une source : binaire inline (data_base64), URL téléchargée par
    # le serveur (source_url), ou ticket d'upload dont les octets ont déjà été
    # PUT (upload_id).
    raw_b64 = args.get("data_base64")
    raw_url = args.get("source_url")
    raw_upload = args.get("upload_id")
    has_b64 = raw_b64 is not None and str(raw_b64) != ""
    has_url = raw_url is not None and str(raw_url) != ""
    has_upload = raw_upload is not None and str(raw_upload) != ""
    if has_b64 + has_url + has_upload != 1:
        return _text({"error": "fournir exactement l'un de data_base64, source_url ou upload_id"})

    # Voie ticket : l'artefact est créé et le ticket consommé atomiquement.
    # Le nom de fichier vient du ticket ; l'estampillage created_by suit l'OBO.
    if has_upload:
        try:
            created = await uploads.consume_upload(
                pool,
                ws_slug,
                str(raw_upload),
                requested_by=require_identity().id,
                created_by=acting_identity().id,
                max_bytes=max_bytes,
            )
        except HTTPException as e:
            return _text({"error": e.detail})
        return _artifact_payload(created)

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

    # Estampillage OBO : l'artefact est attribué à l'acteur (l'humain si l'OBO
    # du portail l'a résolu, sinon l'identité de la clé) — cohérent avec
    # datasets et workspaces.
    user = acting_identity()
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
    return _artifact_payload(created)


def _artifact_payload(created: ArtifactCreatedOut) -> list[TextContent]:
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


def _is_text_media_type(media_type: str) -> bool:
    """Un media type textuel (décodable en clair) selon sa déclaration."""
    mt = media_type.lower()
    if mt.startswith("text/"):
        return True
    if mt in {"application/json", "application/xml", "application/x-ndjson"}:
        return True
    return mt.endswith("+json") or mt.endswith("+xml")


async def handle_get_artifact_data(
    pool: asyncpg.Pool, settings: Settings | None, args: dict[str, object]
) -> list[TextContent]:
    """Contenu de l'artefact INLINE (texte brut ou base64), pour un agent sans
    accès réseau. Au-delà de la limite inline, redirige vers get_artifact_link."""
    if settings is None:
        return _text({"error": "configuration indisponible"})
    ws_slug = str(args.get("workspace_slug", ""))
    artifact_id = _parse_artifact_id(args.get("artifact_id", ""))
    if artifact_id is None:
        return _text({"error": "artifact_id invalide : UUID attendu"})
    try:
        meta = await service.get_artifact_meta(pool, ws_slug, artifact_id)
    except HTTPException as e:
        return _text({"error": e.detail})

    max_inline = settings.artifact_inline_max_bytes
    if meta.size_bytes > max_inline:
        # Trop gros pour l'inline : ce n'est PAS une erreur, on oriente l'agent.
        return _text(
            {
                "too_large": True,
                "size_bytes": meta.size_bytes,
                "max_inline_bytes": max_inline,
                "media_type": meta.media_type,
                "filename": meta.filename,
                "hint": "contenu trop volumineux pour l'inline — utiliser get_artifact_link",
            }
        )

    try:
        data, media_type, filename = await service.fetch_artifact_content(
            pool, ws_slug, artifact_id
        )
    except HTTPException as e:
        return _text({"error": e.detail})

    if _is_text_media_type(media_type):
        try:
            return _text(
                {
                    "content": data.decode("utf-8"),
                    "encoding": "utf-8",
                    "media_type": media_type,
                    "size_bytes": meta.size_bytes,
                    "filename": filename,
                    "truncated": False,
                }
            )
        except UnicodeDecodeError:
            pass  # media type textuel mais octets non-UTF-8 → repli base64
    return _text(
        {
            "content": base64.b64encode(data).decode("ascii"),
            "encoding": "base64",
            "media_type": media_type,
            "size_bytes": meta.size_bytes,
            "filename": filename,
            "truncated": False,
        }
    )


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

    raw_fn = args.get("filename")
    filename = str(raw_fn) if raw_fn not in (None, "") else None
    raw_sha = args.get("sha256")
    sha256 = str(raw_sha) if raw_sha not in (None, "") else None
    document_id: uuid.UUID | None = None
    if args.get("document_id") not in (None, ""):
        document_id = _parse_artifact_id(args.get("document_id"))
        if document_id is None:
            return _text({"error": "document_id invalide : UUID attendu"})

    try:
        items, total = await service.list_artifacts(
            pool,
            ws_slug,
            limit=limit,
            offset=offset,
            filename=filename,
            sha256=sha256,
            document_id=document_id,
        )
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

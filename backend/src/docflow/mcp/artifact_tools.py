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

from docflow.artifacts import mutable, service, uploads
from docflow.artifacts.links import build_download_query, build_preview_query
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
                "mutable": {
                    "type": ["boolean", "string"],
                    "description": (
                        "Crée un artefact MUTABLE (défaut false) : id stable, éditable "
                        "ensuite par update_artifact / patch_artifact, EXCLU de la "
                        "déduplication. Requis pour une maquette d'écran. Seul un "
                        "artefact mutable peut porter l'extension .html (canal dédié). "
                        "Non supporté via upload_id. Booléen — la chaîne \"true\" est "
                        "aussi acceptée (clients qui sérialisent les booléens)."
                    ),
                },
            },
            "required": ["workspace_slug"],
        },
    ),
    Tool(
        name="update_artifact",
        description=(
            "Remplace INTÉGRALEMENT le contenu d'un artefact MUTABLE (l'id ne change "
            "pas ; l'écriture crée la révision suivante). `content` est du texte "
            "(UTF-8). `if_revision` est OBLIGATOIRE — la révision courante attendue "
            "(lue via get_artifact) : une révision périmée est refusée (409) avec la "
            "révision courante en retour, et un agent ne peut donc pas écrire sans "
            "avoir lu. Refusé sur un artefact non mutable. Retourne {id, revision, "
            "sha256, size_bytes}. Pour une retouche ponctuelle, préférer patch_artifact."
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
                "content": {
                    "type": "string",
                    "description": "Nouveau contenu intégral (texte UTF-8)",
                },
                "if_revision": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Révision attendue (obligatoire, concurrence optimiste)",
                },
            },
            "required": ["workspace_slug", "artifact_id", "content", "if_revision"],
        },
    ),
    Tool(
        name="patch_artifact",
        description=(
            "Édite un artefact MUTABLE TEXTUEL par ancres, sans réécrire tout le "
            "contenu. `edits` = liste de {old_str, new_str} : chaque `old_str` doit "
            "apparaître EXACTEMENT une fois dans le contenu courant — zéro ou "
            "plusieurs occurrences rejette TOUTE la requête (rien n'est écrit, erreur "
            "explicite). Éditions appliquées atomiquement sur le contenu original "
            "(pas d'invalidation mutuelle des ancres). `if_revision` OBLIGATOIRE "
            "(comme update_artifact). Refusé sur artefact binaire ou non mutable. "
            "Crée la révision suivante ; retourne {id, revision, sha256, size_bytes}."
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
                "edits": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_str": {
                                "type": "string",
                                "description": "Ancre — doit matcher 1 fois",
                            },
                            "new_str": {"type": "string", "description": "Remplacement"},
                        },
                        "required": ["old_str", "new_str"],
                    },
                    "description": "Éditions par ancre (chaque old_str unique dans le contenu)",
                },
                "if_revision": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Révision attendue (obligatoire, concurrence optimiste)",
                },
            },
            "required": ["workspace_slug", "artifact_id", "edits", "if_revision"],
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
                "revision": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Révision précise à lire (artefact mutable) ; défaut = révision "
                        "courante. L'historique des révisions est donné par get_artifact."
                    ),
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
        name="get_preview_link",
        description=(
            "Émet un lien de PREVIEW signé (courte durée, révision-conscient) vers "
            "une maquette d'écran — artefact MUTABLE de type text/html — rendu dans "
            "une iframe sandboxée servie depuis l'origine de preview DÉDIÉE "
            "(distincte de docflow). Réservé aux maquettes HTML : refusé sur tout "
            "autre artefact. Sans origine de preview configurée sur l'instance, "
            "refusé. Par défaut la révision courante ; `revision` pour une révision "
            "précise. Retourne {url, revision, expires_in_seconds}. Pour lire le "
            "contenu source d'une maquette, utiliser get_artifact_data."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_slug": {"type": "string", "description": "Slug du workspace"},
                "artifact_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID de la maquette",
                },
                "revision": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Révision à rendre (défaut : révision courante)",
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

ARTIFACT_TOOLS.append(
    Tool(
        name="prune_artifact_revisions",
        description=(
            "Purge l'historique d'un artefact MUTABLE : conserve les `keep` dernières "
            "révisions ; la révision COURANTE est toujours conservée. Opération "
            "explicite et définitive (les révisions antérieures à la fenêtre sont "
            "supprimées). Sans `keep`, applique la rétention par défaut de l'instance. "
            "Aucun effet sur un artefact immuable (pas d'historique). Retourne "
            "{id, current_revision, revisions_pruned}."
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
                "keep": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Révisions à conserver (défaut : rétention de l'instance)",
                },
            },
            "required": ["workspace_slug", "artifact_id"],
        },
    )
)


# Périmètre workspace des tools (fusionné dans _WS_TOOLS du serveur) : écriture ?
ARTIFACT_WS_TOOLS: dict[str, bool] = {
    "create_upload": True,
    "create_artifact": True,
    "update_artifact": True,
    "patch_artifact": True,
    "prune_artifact_revisions": True,
    "get_artifact": False,
    "get_artifact_data": False,
    "get_artifact_link": False,
    "get_preview_link": False,
    "list_artifacts": False,
}


def _text(data: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _as_bool(raw: object) -> bool:
    """Booléen tolérant : accepte `True` OU une chaîne « true »/« 1 »/« yes »/« oui ».

    Nombre de clients LLM sérialisent les booléens en chaîne ; sans ça, `mutable`
    stringifié serait vu comme faux et une maquette `.html` finirait refusée.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "1", "yes", "oui"}
    return False


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
    mutable = _as_bool(args.get("mutable"))

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
        if mutable:
            return _text(
                {"error": "mutable non supporté via upload_id (utiliser data_base64 ou source_url)"}
            )
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
            mutable=mutable,
        )
    except HTTPException as e:
        return _text({"error": e.detail})
    return _artifact_payload(created)


async def handle_update_artifact(
    pool: asyncpg.Pool, settings: Settings | None, args: dict[str, object]
) -> list[TextContent]:
    """Remplacement intégral du contenu d'un artefact mutable (révision N+1)."""
    if settings is None:
        return _text({"error": "configuration indisponible"})
    ws_slug = str(args.get("workspace_slug", ""))
    artifact_id = _parse_artifact_id(args.get("artifact_id", ""))
    if artifact_id is None:
        return _text({"error": "artifact_id invalide : UUID attendu"})
    if_revision = args.get("if_revision")
    if not isinstance(if_revision, int) or isinstance(if_revision, bool):
        return _text({"error": "if_revision obligatoire (entier)"})
    content = args.get("content")
    if not isinstance(content, str):
        return _text({"error": "content obligatoire (texte)"})
    try:
        result = await mutable.update_artifact(
            pool,
            ws_slug,
            artifact_id,
            data=content.encode("utf-8"),
            if_revision=if_revision,
            updated_by=acting_identity().id,
            max_bytes=settings.artifact_max_bytes,
            keep=settings.artifact_revision_keep,
        )
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(result)


async def handle_patch_artifact(
    pool: asyncpg.Pool, settings: Settings | None, args: dict[str, object]
) -> list[TextContent]:
    """Édition par ancres d'un artefact mutable textuel (révision N+1)."""
    if settings is None:
        return _text({"error": "configuration indisponible"})
    ws_slug = str(args.get("workspace_slug", ""))
    artifact_id = _parse_artifact_id(args.get("artifact_id", ""))
    if artifact_id is None:
        return _text({"error": "artifact_id invalide : UUID attendu"})
    if_revision = args.get("if_revision")
    if not isinstance(if_revision, int) or isinstance(if_revision, bool):
        return _text({"error": "if_revision obligatoire (entier)"})
    raw_edits = args.get("edits")
    if not isinstance(raw_edits, list) or not raw_edits:
        return _text({"error": "edits obligatoire (liste non vide de {old_str, new_str})"})
    edits: list[dict[str, str]] = []
    for item in raw_edits:
        if not isinstance(item, dict) or "old_str" not in item or "new_str" not in item:
            return _text({"error": "chaque édition doit porter old_str et new_str"})
        edits.append({"old_str": str(item["old_str"]), "new_str": str(item["new_str"])})
    try:
        result = await mutable.patch_artifact(
            pool,
            ws_slug,
            artifact_id,
            edits=edits,
            if_revision=if_revision,
            updated_by=acting_identity().id,
            max_bytes=settings.artifact_max_bytes,
            keep=settings.artifact_revision_keep,
        )
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(result)


async def handle_prune_artifact_revisions(
    pool: asyncpg.Pool, settings: Settings | None, args: dict[str, object]
) -> list[TextContent]:
    """Purge explicite de l'historique d'un artefact mutable (garde les N dernières)."""
    if settings is None:
        return _text({"error": "configuration indisponible"})
    ws_slug = str(args.get("workspace_slug", ""))
    artifact_id = _parse_artifact_id(args.get("artifact_id", ""))
    if artifact_id is None:
        return _text({"error": "artifact_id invalide : UUID attendu"})
    raw_keep = args.get("keep")
    keep = (
        raw_keep
        if isinstance(raw_keep, int) and not isinstance(raw_keep, bool)
        else settings.artifact_revision_keep
    )
    try:
        result = await mutable.prune_artifact_revisions(pool, ws_slug, artifact_id, keep=keep)
    except HTTPException as e:
        return _text({"error": e.detail})
    return _text(result)


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
    payload = meta.model_dump(mode="json")
    # Historique consultable (artefacts mutables uniquement).
    if meta.mutable:
        payload["revisions"] = await mutable.list_revisions(pool, ws_slug, artifact_id)
    return _text(payload)


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
    raw_rev = args.get("revision")
    revision = raw_rev if isinstance(raw_rev, int) and not isinstance(raw_rev, bool) else None

    # Fetch de la révision demandée (mutable) ou de la tête.
    try:
        if revision is not None:
            data, media_type, filename = await mutable.fetch_revision_content(
                pool, ws_slug, artifact_id, revision
            )
        else:
            data, media_type, filename = await service.fetch_artifact_content(
                pool, ws_slug, artifact_id
            )
    except HTTPException as e:
        return _text({"error": e.detail})

    max_inline = settings.artifact_inline_max_bytes
    if len(data) > max_inline:
        # Trop gros pour l'inline : ce n'est PAS une erreur, on oriente l'agent.
        return _text(
            {
                "too_large": True,
                "size_bytes": len(data),
                "max_inline_bytes": max_inline,
                "media_type": media_type,
                "filename": filename,
                "hint": "contenu trop volumineux pour l'inline — utiliser get_artifact_link",
            }
        )

    if _is_text_media_type(media_type):
        try:
            return _text(
                {
                    "content": data.decode("utf-8"),
                    "encoding": "utf-8",
                    "media_type": media_type,
                    "size_bytes": len(data),
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
            "size_bytes": len(data),
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


async def handle_get_preview_link(
    pool: asyncpg.Pool, settings: Settings | None, args: dict[str, object]
) -> list[TextContent]:
    """Lien de preview signé (révision-conscient) d'une maquette HTML mutable."""
    if settings is None:
        return _text({"error": "configuration indisponible"})
    if not settings.preview_base_url:
        return _text({"error": "origine de preview non configurée sur l'instance"})
    ws_slug = str(args.get("workspace_slug", ""))
    artifact_id = _parse_artifact_id(args.get("artifact_id", ""))
    if artifact_id is None:
        return _text({"error": "artifact_id invalide : UUID attendu"})
    try:
        meta = await service.get_artifact_meta(pool, ws_slug, artifact_id)
    except HTTPException as e:
        return _text({"error": e.detail})
    if not meta.mutable or meta.media_type.lower() != "text/html":
        return _text({"error": "get_preview_link réservé aux maquettes HTML mutables"})

    raw_rev = args.get("revision")
    revision = (
        raw_rev if isinstance(raw_rev, int) and not isinstance(raw_rev, bool) else meta.revision
    )
    if revision < 1 or revision > meta.revision:
        return _text({"error": f"révision hors bornes (1..{meta.revision})"})

    ttl = settings.artifact_link_ttl_seconds
    query = build_preview_query(
        ws_slug, artifact_id, revision, ttl_seconds=ttl, secret=settings.jwt_secret.reveal()
    )
    base = settings.preview_base_url.rstrip("/")
    return _text(
        {
            "url": f"{base}/preview/{ws_slug}/{artifact_id}?{query}",
            "revision": revision,
            "expires_in_seconds": ttl,
        }
    )

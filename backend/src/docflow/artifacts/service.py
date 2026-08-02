from __future__ import annotations

import hashlib
import uuid
import zlib

import asyncpg
from fastapi import HTTPException

from docflow.artifacts.media_types import load_allowed_map
from docflow.artifacts.parser import extract_artifact_ids
from docflow.db.helpers import require_workspace
from docflow.schemas.artifact import ArtifactCreatedOut, ArtifactMetaOut


def artifact_url(ws_slug: str, artifact_id: uuid.UUID) -> str:
    """URL de service telle qu'insérée dans le markdown (et parsée par parser.py)."""
    return f"/api/workspaces/{ws_slug}/artifacts/{artifact_id}"


def _validate_filename(filename: str, allowed: dict[str, str]) -> tuple[str, str, str]:
    """Nettoie le nom de fichier et retourne (nom, extension, media_type).

    Le nom est réduit à son basename (aucun composant de chemin) ; extension
    obligatoire et présente dans le registre `allowed` (extension → media_type).
    """
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()
    if not name or len(name) > 255:
        raise HTTPException(status_code=422, detail="nom de fichier invalide")
    if "." not in name:
        raise HTTPException(status_code=422, detail="extension de fichier requise")
    ext = name.rsplit(".", 1)[1].lower()
    media_type = allowed.get(ext)
    if media_type is None:
        allowed_list = ", ".join(sorted(allowed))
        raise HTTPException(
            status_code=422,
            detail=f"extension '{ext}' non autorisée (autorisées : {allowed_list})",
        )
    return name, ext, media_type


# ── Création (dédupliquée par sha256) ────────────────────────────────────────


async def create_artifact(
    pool: asyncpg.Pool,
    ws_slug: str,
    *,
    filename: str,
    data: bytes,
    created_by: uuid.UUID | None,
    max_bytes: int,
    media_type_override: str | None = None,
) -> ArtifactCreatedOut:
    """Enregistre un binaire dans le workspace, dédupliqué par sha256.

    Si un artefact de même empreinte existe déjà dans le workspace, il est
    retourné tel quel (deduplicated=True) — le binaire n'est jamais stocké
    deux fois dans un même workspace.
    """
    if not data:
        raise HTTPException(status_code=422, detail="fichier vide")
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"fichier trop volumineux ({len(data)} octets, max {max_bytes})",
        )
    sha256 = hashlib.sha256(data).hexdigest()
    crc32 = zlib.crc32(data)

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Whitelist chargée depuis le registre (table artifact_media_type),
            # source de vérité administrable.
            allowed = await load_allowed_map(conn)
            name, ext, media_type = _validate_filename(filename, allowed)
            if media_type_override is not None:
                # L'override reste borné à la whitelist : jamais un type
                # arbitraire (text/html servi depuis notre origine = XSS).
                if media_type_override not in set(allowed.values()):
                    raise HTTPException(
                        status_code=422,
                        detail=f"media_type non autorisé : {media_type_override}",
                    )
                media_type = media_type_override
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            inserted = await conn.fetchrow(
                """
                INSERT INTO artifact
                    (workspace_technical_key, sha256, crc32, filename, extension,
                     media_type, size_bytes, data, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (workspace_technical_key, sha256) DO NOTHING
                RETURNING id
                """,
                wk,
                sha256,
                crc32,
                name,
                ext,
                media_type,
                len(data),
                data,
                created_by,
            )
            if inserted is not None:
                return ArtifactCreatedOut(
                    id=inserted["id"],
                    url=artifact_url(ws_slug, inserted["id"]),
                    deduplicated=False,
                    filename=name,
                    extension=ext,
                    media_type=media_type,
                    size_bytes=len(data),
                    sha256=sha256,
                    crc32=crc32,
                )
            existing = await conn.fetchrow(
                "SELECT id, filename, extension, media_type, size_bytes, crc32 "
                "FROM artifact WHERE workspace_technical_key = $1 AND sha256 = $2",
                wk,
                sha256,
            )
            assert existing is not None  # UNIQUE garantit sa présence après le conflit
            return ArtifactCreatedOut(
                id=existing["id"],
                url=artifact_url(ws_slug, existing["id"]),
                deduplicated=True,
                filename=existing["filename"],
                extension=existing["extension"],
                media_type=existing["media_type"],
                size_bytes=existing["size_bytes"],
                sha256=sha256,
                crc32=existing["crc32"],
            )


# ── Lecture ──────────────────────────────────────────────────────────────────


async def get_artifact_meta(
    pool: asyncpg.Pool, ws_slug: str, artifact_id: uuid.UUID
) -> ArtifactMetaOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            """
            SELECT a.id, a.filename, a.extension, a.media_type, a.size_bytes,
                   a.sha256, a.crc32, a.created_at,
                   (SELECT count(*) FROM artifact_reference r
                    WHERE r.artifact_ref = a.id)::int AS refcount
            FROM artifact a
            WHERE a.id = $1 AND a.workspace_technical_key = $2
            """,
            artifact_id,
            wk,
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"artefact {artifact_id} introuvable")
    return ArtifactMetaOut(**dict(row))


async def list_artifacts(
    pool: asyncpg.Pool, ws_slug: str, *, limit: int, offset: int
) -> tuple[list[dict[str, object]], int]:
    """Liste paginée des artefacts d'un workspace, du plus récent au plus
    ancien. Renvoie toutes les colonnes de la table SAUF le binaire (`data`) et
    la clé technique interne (`workspace_technical_key`), plus le `refcount`
    calculé. Retourne (items, total)."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        total = await conn.fetchval(
            "SELECT count(*)::int FROM artifact WHERE workspace_technical_key = $1", wk
        )
        rows = await conn.fetch(
            """
            SELECT a.id, a.filename, a.extension, a.media_type, a.size_bytes,
                   a.sha256, a.crc32, a.created_by, a.created_at,
                   (SELECT count(*) FROM artifact_reference r
                    WHERE r.artifact_ref = a.id)::int AS refcount
            FROM artifact a
            WHERE a.workspace_technical_key = $1
            ORDER BY a.created_at DESC, a.id
            LIMIT $2 OFFSET $3
            """,
            wk,
            limit,
            offset,
        )
    return [dict(r) for r in rows], int(total or 0)


async def fetch_artifact_content(
    pool: asyncpg.Pool, ws_slug: str, artifact_id: uuid.UUID
) -> tuple[bytes, str, str]:
    """Retourne (data, media_type, filename), ou 404 hors workspace."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            "SELECT data, media_type, filename FROM artifact "
            "WHERE id = $1 AND workspace_technical_key = $2",
            artifact_id,
            wk,
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"artefact {artifact_id} introuvable")
    return bytes(row["data"]), row["media_type"], row["filename"]


async def fetch_public_artifact_content(
    pool: asyncpg.Pool, artifact_id: uuid.UUID
) -> tuple[bytes, str, str]:
    """Version publique (sans auth) : servi ssi ≥1 document exposé le référence.

    Miroir de la règle des endpoints /pub : `exposed = true` est la seule
    porte d'entrée publique. Un artefact non référencé, ou référencé
    uniquement par des documents privés, reste introuvable (404).
    """
    row = await pool.fetchrow(
        """
        SELECT a.data, a.media_type, a.filename
        FROM artifact a
        WHERE a.id = $1
          AND EXISTS (
              SELECT 1
              FROM artifact_reference r
              JOIN document d ON d.doc_technical_key = r.document_ref
              WHERE r.artifact_ref = a.id AND d.exposed = true
          )
        """,
        artifact_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="artefact introuvable ou non public")
    return bytes(row["data"]), row["media_type"], row["filename"]


# ── Références + cycle de vie ────────────────────────────────────────────────


async def refresh_artifact_references(
    conn: asyncpg.Connection,
    doc_id: uuid.UUID,
    ws_key: uuid.UUID,
    content: str | None,
) -> None:
    """Reconstruit les références artefacts du document depuis son contenu.

    Doit être appelé dans la même transaction que le save (miroir de
    references.refresh_references). Un artefact dont la dernière référence
    disparaît est supprimé immédiatement ; un artefact référencé ailleurs
    est conservé. Les références vers des artefacts inexistants ou d'un
    autre workspace sont ignorées (le save n'échoue jamais pour un lien mort).
    """
    parsed = extract_artifact_ids(content or "")
    old_rows = await conn.fetch(
        "SELECT artifact_ref FROM artifact_reference WHERE document_ref = $1", doc_id
    )
    old_ids = {r["artifact_ref"] for r in old_rows}
    await conn.execute("DELETE FROM artifact_reference WHERE document_ref = $1", doc_id)

    new_ids: set[uuid.UUID] = set()
    if parsed:
        rows = await conn.fetch(
            "SELECT id FROM artifact WHERE workspace_technical_key = $1 AND id = ANY($2::uuid[])",
            ws_key,
            [uuid.UUID(a) for a in parsed],
        )
        new_ids = {r["id"] for r in rows}
        if new_ids:
            await conn.executemany(
                "INSERT INTO artifact_reference (artifact_ref, document_ref, "
                "workspace_technical_key) VALUES ($1, $2, $3)",
                [(aid, doc_id, ws_key) for aid in new_ids],
            )

    removed = old_ids - new_ids
    if removed:
        await purge_unreferenced(conn, list(removed))


async def collect_subtree_artifacts(conn: asyncpg.Connection, doc_id: uuid.UUID) -> list[uuid.UUID]:
    """Artefacts référencés par un document et tous ses descendants.

    À appeler AVANT la suppression du document : les références disparaissent
    en cascade avec les documents, il faut capturer les candidats d'abord.
    """
    rows = await conn.fetch(
        """
        WITH RECURSIVE descendants AS (
            SELECT doc_technical_key FROM document WHERE doc_technical_key = $1
            UNION ALL
            SELECT d.doc_technical_key
            FROM document d
            JOIN descendants p ON d.parent = p.doc_technical_key
        )
        SELECT DISTINCT ar.artifact_ref
        FROM artifact_reference ar
        JOIN descendants ds ON ar.document_ref = ds.doc_technical_key
        """,
        doc_id,
    )
    return [r["artifact_ref"] for r in rows]


async def purge_unreferenced(conn: asyncpg.Connection, artifact_ids: list[uuid.UUID]) -> int:
    """Supprime, parmi les candidats, les artefacts qui n'ont plus aucune référence."""
    if not artifact_ids:
        return 0
    result = await conn.execute(
        """
        DELETE FROM artifact a
        WHERE a.id = ANY($1::uuid[])
          AND NOT EXISTS (SELECT 1 FROM artifact_reference r WHERE r.artifact_ref = a.id)
        """,
        artifact_ids,
    )
    return int(result.split()[-1])


async def purge_stale(pool: asyncpg.Pool, *, older_than_hours: int) -> int:
    """Purge les artefacts jamais référencés plus vieux que le seuil.

    Couvre le cas d'une image collée dans un brouillon jamais enregistré :
    aucune référence ne sera jamais créée, la règle refcount-0 ne s'applique
    donc pas. Appelé périodiquement par le worker.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM artifact a
            WHERE NOT EXISTS (SELECT 1 FROM artifact_reference r WHERE r.artifact_ref = a.id)
              AND a.created_at < now() - make_interval(hours => $1)
            """,
            older_than_hours,
        )
    return int(result.split()[-1])

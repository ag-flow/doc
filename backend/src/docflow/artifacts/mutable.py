"""Artefacts mutables — écriture (update/patch), révisions, lecture historique.

Socle de l'epic « Maquettes d'écran ». Un artefact `mutable` garde son id à
travers N écritures : chaque écriture crée la révision N+1 (tête sur `artifact`,
historique dans `artifact_revision`). Toute écriture exige `if_revision` — un
agent ne peut pas écrire sans avoir lu (concurrence optimiste, fail closed).
"""

from __future__ import annotations

import hashlib
import uuid
import zlib

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace


def is_textual_media_type(media_type: str) -> bool:
    """Un media type décodable en texte (patch par ancre réservé à ceux-ci)."""
    mt = media_type.lower()
    if mt.startswith("text/"):
        return True
    if mt in {"application/json", "application/xml", "application/x-ndjson"}:
        return True
    return mt.endswith("+json") or mt.endswith("+xml")


def apply_anchor_edits(text: str, edits: list[dict[str, str]]) -> str:
    """Applique des éditions par ancre textuelle, ATOMIQUEMENT.

    Règle centrale : chaque `old_str` doit matcher **exactement une fois** dans
    le texte courant. Zéro ou plusieurs occurrences → rejet de TOUTE la requête
    (422), rien n'est écrit — l'échec est bruyant, jamais silencieux. Les ancres
    ne doivent pas se chevaucher. Les remplacements sont calculés sur le texte
    ORIGINAL : aucune édition n'invalide l'ancre d'une autre.
    """
    if not edits:
        raise HTTPException(status_code=422, detail="aucune édition fournie")
    spans: list[tuple[int, int, str]] = []
    for edit in edits:
        old = edit.get("old_str", "")
        new = edit.get("new_str", "")
        if not isinstance(old, str) or not isinstance(new, str) or old == "":
            raise HTTPException(
                status_code=422, detail="édition invalide (old_str non vide requis)"
            )
        count = text.count(old)
        if count == 0:
            raise HTTPException(status_code=422, detail=f"ancre introuvable : {old!r}")
        if count > 1:
            raise HTTPException(
                status_code=422, detail=f"ancre ambiguë ({count} occurrences) : {old!r}"
            )
        start = text.index(old)
        spans.append((start, start + len(old), new))

    spans.sort()
    for i in range(1, len(spans)):
        if spans[i][0] < spans[i - 1][1]:
            raise HTTPException(status_code=422, detail="ancres qui se chevauchent")

    out: list[str] = []
    pos = 0
    for start, end, new in spans:
        out.append(text[pos:start])
        out.append(new)
        pos = end
    out.append(text[pos:])
    return "".join(out)


async def _load_head_for_write(
    conn: asyncpg.Connection, ws_slug: str, artifact_id: uuid.UUID, if_revision: int
) -> asyncpg.Record:
    """Verrouille la tête d'un artefact mutable et valide `if_revision`."""
    wk = await require_workspace(conn, ws_slug, allow_archived=False)
    row = await conn.fetchrow(
        "SELECT id, revision, mutable, media_type, filename, data "
        "FROM artifact WHERE id = $1 AND workspace_technical_key = $2 FOR UPDATE",
        artifact_id,
        wk,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"artefact {artifact_id} introuvable")
    if not row["mutable"]:
        raise HTTPException(status_code=409, detail="artefact non mutable — écriture refusée")
    if row["revision"] != if_revision:
        # État courant renvoyé : l'agent relit puis rejoue.
        raise HTTPException(
            status_code=409,
            detail={"error": "révision périmée", "current_revision": row["revision"]},
        )
    return row


async def _commit_revision(
    conn: asyncpg.Connection,
    artifact_id: uuid.UUID,
    *,
    new_data: bytes,
    new_revision: int,
    created_by: uuid.UUID | None,
) -> dict[str, object]:
    """Écrit la tête et empile la révision (même transaction)."""
    sha256 = hashlib.sha256(new_data).hexdigest()
    crc32 = zlib.crc32(new_data)
    await conn.execute(
        "UPDATE artifact SET data = $2, sha256 = $3, crc32 = $4, size_bytes = $5, "
        "revision = $6 WHERE id = $1",
        artifact_id,
        new_data,
        sha256,
        crc32,
        len(new_data),
        new_revision,
    )
    await conn.execute(
        "INSERT INTO artifact_revision "
        "(artifact_ref, revision, sha256, size_bytes, data, created_by) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        artifact_id,
        new_revision,
        sha256,
        len(new_data),
        new_data,
        created_by,
    )
    return {
        "id": artifact_id,
        "revision": new_revision,
        "sha256": sha256,
        "size_bytes": len(new_data),
    }


async def update_artifact(
    pool: asyncpg.Pool,
    ws_slug: str,
    artifact_id: uuid.UUID,
    *,
    data: bytes,
    if_revision: int,
    updated_by: uuid.UUID | None,
    max_bytes: int,
) -> dict[str, object]:
    """Remplacement intégral du contenu d'un artefact mutable (révision N+1)."""
    if not data:
        raise HTTPException(status_code=422, detail="contenu vide")
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"contenu trop volumineux ({len(data)} octets, max {max_bytes})"
        )
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _load_head_for_write(conn, ws_slug, artifact_id, if_revision)
            return await _commit_revision(
                conn,
                artifact_id,
                new_data=data,
                new_revision=row["revision"] + 1,
                created_by=updated_by,
            )


async def patch_artifact(
    pool: asyncpg.Pool,
    ws_slug: str,
    artifact_id: uuid.UUID,
    *,
    edits: list[dict[str, str]],
    if_revision: int,
    updated_by: uuid.UUID | None,
    max_bytes: int,
) -> dict[str, object]:
    """Édition partielle par ancre textuelle d'un artefact mutable (révision N+1)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _load_head_for_write(conn, ws_slug, artifact_id, if_revision)
            if not is_textual_media_type(row["media_type"]):
                raise HTTPException(
                    status_code=422,
                    detail=f"patch réservé aux artefacts textuels (media_type={row['media_type']})",
                )
            try:
                text = bytes(row["data"]).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise HTTPException(
                    status_code=422, detail="artefact non décodable en UTF-8"
                ) from exc
            new_data = apply_anchor_edits(text, edits).encode("utf-8")
            if not new_data:
                raise HTTPException(status_code=422, detail="le patch produirait un contenu vide")
            if len(new_data) > max_bytes:
                raise HTTPException(
                    status_code=413, detail=f"résultat trop volumineux (max {max_bytes} octets)"
                )
            return await _commit_revision(
                conn,
                artifact_id,
                new_data=new_data,
                new_revision=row["revision"] + 1,
                created_by=updated_by,
            )


async def fetch_revision_content(
    pool: asyncpg.Pool, ws_slug: str, artifact_id: uuid.UUID, revision: int
) -> tuple[bytes, str, str]:
    """(data, media_type, filename) d'une révision passée d'un artefact mutable."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        head = await conn.fetchrow(
            "SELECT media_type, filename FROM artifact "
            "WHERE id = $1 AND workspace_technical_key = $2",
            artifact_id,
            wk,
        )
        if head is None:
            raise HTTPException(status_code=404, detail=f"artefact {artifact_id} introuvable")
        rev = await conn.fetchrow(
            "SELECT data FROM artifact_revision WHERE artifact_ref = $1 AND revision = $2",
            artifact_id,
            revision,
        )
    if rev is None:
        raise HTTPException(status_code=404, detail=f"révision {revision} introuvable")
    return bytes(rev["data"]), head["media_type"], head["filename"]


async def list_revisions(
    pool: asyncpg.Pool, ws_slug: str, artifact_id: uuid.UUID
) -> list[dict[str, object]]:
    """Historique des révisions (sans le binaire), de la plus ancienne à la plus récente."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        exists = await conn.fetchval(
            "SELECT 1 FROM artifact WHERE id = $1 AND workspace_technical_key = $2",
            artifact_id,
            wk,
        )
        if not exists:
            raise HTTPException(status_code=404, detail=f"artefact {artifact_id} introuvable")
        rows = await conn.fetch(
            "SELECT revision, sha256, size_bytes, created_at FROM artifact_revision "
            "WHERE artifact_ref = $1 ORDER BY revision",
            artifact_id,
        )
    return [dict(r) for r in rows]

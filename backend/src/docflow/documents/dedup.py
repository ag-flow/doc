"""Clef de dédoublonnage d'un document : sha256 d'une clef texte normalisée.

Métadonnée d'identité (non versionnée) posée sur le head `document`. La clef
brute n'est jamais stockée — seule son empreinte sha256 l'est. La colonne est
nullable et non unique : c'est l'appelant qui décide d'un doublon, l'application
ne l'empêche pas. Deux tools MCP l'exploitent : find_by_dedup_key (recherche)
et set_dedup_key (écriture).
"""

from __future__ import annotations

import hashlib
import uuid

import asyncpg
from fastapi import HTTPException

from docflow.db.helpers import require_workspace


def normalize_and_hash(text: str) -> str:
    """sha256 hex de la clef normalisée (trim + minuscules)."""
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def set_dedup_key(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, text: str | None
) -> dict[str, object]:
    """Pose (ou efface) la clef de dédoublonnage d'un document.

    `text` non vide après trim → `dedup_sha256` = sha256(normalize(text)).
    `text` None ou vide → `dedup_sha256` = NULL (effacement). 404 si le document
    n'existe pas dans le workspace.
    """
    digest: str | None = None
    if text is not None and text.strip() != "":
        digest = normalize_and_hash(text)

    async with pool.acquire() as conn:
        async with conn.transaction():
            wk = await require_workspace(conn, ws_slug)
            updated = await conn.fetchval(
                "UPDATE document SET dedup_sha256 = $1 "
                "WHERE doc_technical_key = $2 AND workspace_technical_key = $3 "
                "RETURNING doc_technical_key",
                digest,
                doc_id,
                wk,
            )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"document {doc_id} introuvable")
    return {"updated": True, "doc_id": str(doc_id), "dedup_sha256": digest}


async def find_by_dedup_key(pool: asyncpg.Pool, ws_slug: str, text: str) -> dict[str, object]:
    """Documents du workspace dont la clef de dédoublonnage correspond au texte.

    Le texte est normalisé (trim + minuscules) puis hashé, exactement comme à
    l'écriture. Renvoie 0..N documents — aucune unicité n'est imposée.
    """
    digest = normalize_and_hash(text)
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            "SELECT d.doc_technical_key, d.title, ft.slug AS functional_type_slug "
            "FROM document d "
            "LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref "
            "WHERE d.workspace_technical_key = $1 AND d.dedup_sha256 = $2 "
            "ORDER BY d.title",
            wk,
            digest,
        )
    documents = [
        {
            "id": str(r["doc_technical_key"]),
            "title": r["title"],
            "functional_type_slug": r["functional_type_slug"],
        }
        for r in rows
    ]
    return {"dedup_sha256": digest, "total": len(documents), "documents": documents}

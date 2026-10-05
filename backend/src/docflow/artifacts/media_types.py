from __future__ import annotations

import asyncpg
from fastapi import HTTPException

# ── Garde de sécurité (EN DUR, non administrable) ────────────────────────────
# Ces types sont interdits QUOI QU'IL ARRIVE : servis depuis notre origine, ils
# permettent l'exécution de script (XSS). L'admin ne peut jamais les ajouter au
# registre, même si le reste de la whitelist est éditable. `svg` (image/svg+xml)
# reste toléré comme historiquement — servi en `<img>` + nosniff.
DENYLISTED_MEDIA_TYPES: frozenset[str] = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "text/javascript",
        "application/javascript",
        "application/ecmascript",
        "text/ecmascript",
        "application/x-httpd-php",
    }
)

_EXT_MAX = 16


def _normalize_media_type(media_type: str) -> str:
    """Valide un media type candidat contre le denylist (garde de sécurité)."""
    value = media_type.strip().lower()
    if not value or "/" not in value or len(value) > 200:
        raise HTTPException(status_code=422, detail="media_type invalide")
    if value in DENYLISTED_MEDIA_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"media_type interdit (type actif, risque XSS) : {value}",
        )
    return value


def _normalize_extension(extension: str) -> str:
    ext = extension.strip().lower().lstrip(".")
    if not ext.isalnum() or len(ext) > _EXT_MAX:
        raise HTTPException(
            status_code=422,
            detail="extension invalide (alphanumérique, 1–16 caractères)",
        )
    return ext


# ── Lecture ──────────────────────────────────────────────────────────────────


async def load_allowed_map(conn: asyncpg.Connection) -> dict[str, str]:
    """Map extension → media_type, source de vérité pour la validation d'upload."""
    rows = await conn.fetch("SELECT extension, media_type FROM artifact_media_type")
    return {r["extension"]: r["media_type"] for r in rows}


async def list_types(pool: asyncpg.Pool) -> list[dict[str, object]]:
    rows = await pool.fetch(
        "SELECT extension, media_type, label, created_at, updated_at "
        "FROM artifact_media_type ORDER BY extension"
    )
    return [dict(r) for r in rows]


# ── Écriture (admin) ─────────────────────────────────────────────────────────


async def add_type(
    pool: asyncpg.Pool, *, extension: str, media_type: str, label: str
) -> dict[str, object]:
    ext = _normalize_extension(extension)
    mt = _normalize_media_type(media_type)
    try:
        row = await pool.fetchrow(
            "INSERT INTO artifact_media_type (extension, media_type, label) "
            "VALUES ($1, $2, $3) "
            "RETURNING extension, media_type, label, created_at, updated_at",
            ext,
            mt,
            label.strip(),
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=409, detail=f"extension '{ext}' déjà enregistrée"
        ) from exc
    assert row is not None
    return dict(row)


async def update_type(
    pool: asyncpg.Pool, extension: str, *, media_type: str, label: str
) -> dict[str, object]:
    ext = _normalize_extension(extension)
    mt = _normalize_media_type(media_type)
    row = await pool.fetchrow(
        "UPDATE artifact_media_type SET media_type = $2, label = $3, updated_at = now() "
        "WHERE extension = $1 "
        "RETURNING extension, media_type, label, created_at, updated_at",
        ext,
        mt,
        label.strip(),
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"extension '{ext}' introuvable")
    return dict(row)


async def delete_type(pool: asyncpg.Pool, extension: str) -> None:
    ext = _normalize_extension(extension)
    result = await pool.execute("DELETE FROM artifact_media_type WHERE extension = $1", ext)
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail=f"extension '{ext}' introuvable")

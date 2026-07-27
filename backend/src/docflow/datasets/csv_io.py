"""Import / export CSV des datasets tabulaires (stdlib ``csv`` uniquement).

L'import infère le type de chaque colonne en scannant TOUTES ses valeurs (int →
float → date → bool → text), slugifie les en-têtes (dédoublonnage stable) et
délègue l'écriture au service (``create_dataset`` / ``add_column`` / ``add_row``)
pour bénéficier de la coercion typée. Une ligne d'arité incorrecte ou dont une
cellule n'est pas convertible est reportée dans ``errors`` sans faire échouer
l'import. L'export sérialise les valeurs texte d'origine, colonnes et lignes
triées par ``position``.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from typing import Literal, cast

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.datasets import service
from docflow.datasets.coercion import coerce_cell
from docflow.db.helpers import require_workspace, validate_slug

log = structlog.get_logger(__name__)

_MAX_ERROR_SAMPLES = 20
_INFER_ORDER: tuple[str, ...] = ("int", "float", "date", "bool")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")
_DASHES_RE = re.compile(r"-+")


def _slugify(name: str) -> str:
    """Réduit un en-tête en slug valide (``^[a-z0-9][a-z0-9_-]*``, ≤100)."""
    lowered = name.strip().lower()
    slug = _DASHES_RE.sub("-", _NON_SLUG_RE.sub("-", lowered)).strip("-")
    slug = slug[:100].strip("-")
    return slug or "col"


def _dedup(slug: str, used: set[str]) -> str:
    """Rend ``slug`` unique dans ``used`` (suffixe ``-2``, ``-3``…) et l'y ajoute."""
    candidate = slug
    n = 2
    while candidate in used:
        candidate = f"{slug}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def _convertible(col_type: str, raw: str) -> bool:
    try:
        coerce_cell(col_type, raw)  # type: ignore[arg-type]
        return True
    except ValueError:
        return False


def _infer_type(values: list[str]) -> str:
    """Type le plus spécifique acceptant TOUTES les valeurs non vides (sinon text)."""
    non_empty = [v for v in values if v is not None and v.strip() != ""]
    if not non_empty:
        return "text"
    for candidate in _INFER_ORDER:
        if all(_convertible(candidate, v) for v in non_empty):
            return candidate
    return "text"


def _is_blank(row: list[str]) -> bool:
    return all(cell is None or cell.strip() == "" for cell in row)


def _parse(csv_text: str, has_header: bool) -> tuple[list[str], list[list[str]]]:
    """Retourne (en-têtes, lignes de données) ; ignore les lignes entièrement vides."""
    rows = [r for r in csv.reader(io.StringIO(csv_text)) if not _is_blank(r)]
    if has_header:
        if not rows:
            raise HTTPException(status_code=422, detail="CSV vide : aucun en-tête")
        return rows[0], rows[1:]
    width = max((len(r) for r in rows), default=0)
    headers = [f"col-{i + 1}" for i in range(width)]
    return headers, rows


def _column_values(data: list[list[str]], index: int) -> list[str]:
    return [row[index] for row in data if index < len(row)]


def _record_error(errors: list[dict[str, object]], total: int, line: int, reason: str) -> None:
    if total <= _MAX_ERROR_SAMPLES:
        errors.append({"line": line, "reason": reason})


async def _resolve_dataset(
    pool: asyncpg.Pool,
    ws_slug: str,
    dataset_id: uuid.UUID | None,
    slug: str | None,
    label: str | None,
    created_by: uuid.UUID | None,
) -> uuid.UUID:
    """Valide le dataset cible (404) ou le crée (slug+label requis, 422 sinon)."""
    if dataset_id is not None:
        async with pool.acquire() as conn:
            wk = await require_workspace(conn, ws_slug, allow_archived=False)
            await service._require_dataset(conn, wk, dataset_id)
        return dataset_id
    if not slug or not label:
        raise HTTPException(
            status_code=422,
            detail="création d'un dataset : slug et label requis",
        )
    created = await service.create_dataset(pool, ws_slug, slug, label, created_by)
    return uuid.UUID(str(created["id"]))


async def _clear_dataset(pool: asyncpg.Pool, dataset_id: uuid.UUID) -> None:
    """Vide lignes (→ cellules en cascade) puis colonnes du dataset."""
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM dataset_row WHERE dataset_ref = $1", dataset_id)
        await conn.execute("DELETE FROM dataset_column WHERE dataset_ref = $1", dataset_id)


async def _build_columns_replace(
    pool: asyncpg.Pool,
    ws_slug: str,
    dataset_id: uuid.UUID,
    headers: list[str],
    data: list[list[str]],
) -> list[str]:
    """Recrée les colonnes (type inféré) après purge ; retourne les slugs par index."""
    used: set[str] = set()
    header_slugs: list[str] = []
    for index, name in enumerate(headers):
        slug = _dedup(_slugify(name), used)
        col_type = _infer_type(_column_values(data, index))
        validate_slug(slug)
        await service.add_column(pool, ws_slug, dataset_id, slug, name, col_type)
        header_slugs.append(slug)
    return header_slugs


async def _build_columns_append(
    pool: asyncpg.Pool,
    ws_slug: str,
    dataset_id: uuid.UUID,
    headers: list[str],
) -> tuple[list[str], int]:
    """Mappe chaque en-tête sur une colonne existante (par slug) ou en crée une text."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug, allow_archived=False)
        await service._require_dataset(conn, wk, dataset_id)
        existing = await service._columns_by_slug(conn, dataset_id)
    used: set[str] = set(existing.keys())
    header_slugs: list[str] = []
    created = 0
    for name in headers:
        base = _slugify(name)
        if base in existing:
            header_slugs.append(base)
            continue
        slug = _dedup(base, used)
        validate_slug(slug)
        await service.add_column(pool, ws_slug, dataset_id, slug, name, "text")
        header_slugs.append(slug)
        created += 1
    return header_slugs, created


async def _insert_rows(
    pool: asyncpg.Pool,
    ws_slug: str,
    dataset_id: uuid.UUID,
    header_slugs: list[str],
    data: list[list[str]],
) -> tuple[int, int, list[dict[str, object]]]:
    """Insère les lignes valides ; reporte arité/coercion fautives dans ``errors``."""
    rows_created = 0
    rows_skipped = 0
    errors: list[dict[str, object]] = []
    width = len(header_slugs)
    for idx, row in enumerate(data):
        line = idx + 1
        if len(row) != width:
            rows_skipped += 1
            _record_error(errors, rows_skipped, line, f"arité {len(row)} ≠ {width} colonnes")
            continue
        cells = {header_slugs[i]: row[i] for i in range(width)}
        try:
            await service.add_row(pool, ws_slug, dataset_id, cells)
            rows_created += 1
        except HTTPException as e:
            rows_skipped += 1
            _record_error(errors, rows_skipped, line, str(e.detail))
    return rows_created, rows_skipped, errors


async def import_csv(
    pool: asyncpg.Pool,
    ws_slug: str,
    *,
    dataset_id: uuid.UUID | None,
    slug: str | None,
    label: str | None,
    csv_text: str,
    has_header: bool = True,
    mode: Literal["replace", "append"] = "replace",
    created_by: uuid.UUID | None,
) -> dict[str, object]:
    """Importe un CSV dans un dataset (créé ou existant). Voir le module pour le contrat."""
    if mode not in ("replace", "append"):
        raise HTTPException(status_code=422, detail=f"mode inconnu : '{mode}'")
    headers, data = _parse(csv_text, has_header)
    dataset_id = await _resolve_dataset(pool, ws_slug, dataset_id, slug, label, created_by)

    if mode == "replace":
        await _clear_dataset(pool, dataset_id)
        header_slugs = await _build_columns_replace(pool, ws_slug, dataset_id, headers, data)
        columns_created = len(header_slugs)
    else:
        header_slugs, columns_created = await _build_columns_append(
            pool, ws_slug, dataset_id, headers
        )

    rows_created, rows_skipped, errors = await _insert_rows(
        pool, ws_slug, dataset_id, header_slugs, data
    )
    log.info(
        "dataset_csv_import",
        dataset_id=str(dataset_id),
        mode=mode,
        columns_created=columns_created,
        rows_created=rows_created,
        rows_skipped=rows_skipped,
    )
    result: dict[str, object] = {
        "dataset_id": str(dataset_id),
        "columns_created": columns_created,
        "rows_created": rows_created,
        "rows_skipped": rows_skipped,
        "errors": errors,
    }
    if rows_skipped > len(errors):
        result["errors_total"] = rows_skipped
    return result


async def export_csv(
    pool: asyncpg.Pool,
    ws_slug: str,
    dataset_id: uuid.UUID,
    *,
    header: Literal["slug", "label"] = "slug",
) -> str:
    """Sérialise le dataset en CSV (en-têtes slug|label, valeurs texte d'origine)."""
    if header not in ("slug", "label"):
        raise HTTPException(status_code=422, detail=f"header inconnu : '{header}'")
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        await service._require_dataset(conn, wk, dataset_id)
        cols = await conn.fetch(
            "SELECT id, slug, label FROM dataset_column "
            "WHERE dataset_ref = $1 ORDER BY position, slug",
            dataset_id,
        )
        rows = await conn.fetch(
            "SELECT id FROM dataset_row WHERE dataset_ref = $1 ORDER BY position, id",
            dataset_id,
        )
        cells = await conn.fetch(
            "SELECT cell.row_ref, cell.column_ref, cell.value "
            "FROM dataset_cell cell "
            "JOIN dataset_column col ON col.id = cell.column_ref "
            "WHERE col.dataset_ref = $1",
            dataset_id,
        )
    by_row: dict[uuid.UUID, dict[uuid.UUID, str]] = {}
    for c in cells:
        by_row.setdefault(c["row_ref"], {})[c["column_ref"]] = c["value"]

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([cast(str, col[header]) for col in cols])
    for r in rows:
        row_cells = by_row.get(r["id"], {})
        writer.writerow([row_cells.get(col["id"]) or "" for col in cols])
    return out.getvalue()

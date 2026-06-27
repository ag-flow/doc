from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import asyncpg
import structlog

from docflow.templates.diff import DiffResult, compute_diff
from docflow.templates.inheritance import resolve
from docflow.templates.models import AllowedValueDef, ConstraintDef, PropDef, ResolvedType, Template

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)


class VersionConflictError(Exception):
    pass


class ImportConflictError(Exception):
    def __init__(self, diff: DiffResult) -> None:
        self.diff = diff
        conflicts = [f"{i.path}: {i.detail}" for i in diff.conflicts]
        super().__init__("Conflits bloquants :\n" + "\n".join(conflicts))


@dataclass
class ImportReport:
    dry_run: bool
    no_op: bool  # vrai si == version (rien à faire)
    diff: DiffResult
    applied: bool = False


async def _fetch_version(conn: asyncpg.Connection, wk: str, template_slug: str) -> int | None:
    return await conn.fetchval(  # type: ignore[no-any-return]
        "SELECT version FROM workspace_template_import"
        " WHERE workspace_technical_key = $1 AND template = $2",
        wk,
        template_slug,
    )


async def _write_types(
    conn: asyncpg.Connection, wk: str, resolved: list[ResolvedType], diff: DiffResult
) -> None:
    """Applique les ajouts et mises-à-jour douces dans l'ordre topologique."""
    # Slug → UUID pour remapper les parents
    slug_to_id: dict[str, uuid.UUID] = {}
    existing = await conn.fetch(
        "SELECT slug, id FROM functional_type WHERE workspace_technical_key = $1", wk
    )
    for row in existing:
        slug_to_id[row["slug"]] = row["id"]

    add_paths = {i.path for i in diff.adds}
    soft_paths = {i.path for i in diff.soft_updates}

    # Trier : types sans parent d'abord, puis avec parent connu
    ordered = _topo_sort(resolved)

    for rt in ordered:
        if rt.slug in add_paths:
            parent_id: uuid.UUID | None = None
            if rt.parent:
                parent_id = slug_to_id.get(rt.parent)
            row = await conn.fetchrow(
                """
                INSERT INTO functional_type (slug, label, parent, workspace_technical_key)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                rt.slug,
                rt.label,
                parent_id,
                wk,
            )
            assert row is not None
            slug_to_id[rt.slug] = row["id"]
        elif rt.slug in soft_paths:
            await conn.execute(
                "UPDATE functional_type SET label = $1, updated_at = now()"
                " WHERE workspace_technical_key = $2 AND slug = $3",
                rt.label,
                wk,
                rt.slug,
            )

    # Propriétés
    for rt in ordered:
        type_id = slug_to_id.get(rt.slug)
        if type_id is None:
            continue
        await _write_props(conn, type_id, rt.slug, rt.properties, diff)


async def _write_props(
    conn: asyncpg.Connection,
    type_id: uuid.UUID,
    type_slug: str,
    props: list[PropDef],
    diff: DiffResult,
) -> None:
    add_paths = {i.path for i in diff.adds}
    soft_paths = {i.path for i in diff.soft_updates}

    for prop in props:
        prop_path = f"{type_slug}.{prop.slug}"
        prop_id: uuid.UUID | None = None

        if prop_path in add_paths:
            row = await conn.fetchrow(
                """
                INSERT INTO properties_defs
                    (slug, label, functional_type_ref, type, default_value, required)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                prop.slug,
                prop.label,
                type_id,
                prop.type,
                prop.default,
                prop.required,
            )
            assert row is not None
            prop_id = row["id"]
        elif prop_path in soft_paths:
            await conn.execute(
                "UPDATE properties_defs SET label = $1, updated_at = now()"
                " WHERE functional_type_ref = $2 AND slug = $3",
                prop.label,
                type_id,
                prop.slug,
            )

        if prop_id is None:
            prop_id = await conn.fetchval(
                "SELECT id FROM properties_defs WHERE functional_type_ref = $1 AND slug = $2",
                type_id,
                prop.slug,
            )
        if prop_id is None:
            continue

        await _write_constraints(conn, prop_id, f"{prop_path}", prop.constraints, diff)
        await _write_allowed_values(conn, prop_id, f"{prop_path}#av", prop.allowed_values, diff)


async def _write_constraints(
    conn: asyncpg.Connection,
    prop_id: uuid.UUID,
    path_prefix: str,
    constraints: list[ConstraintDef],
    diff: DiffResult,
) -> None:
    add_paths = {i.path for i in diff.adds}
    for c in constraints:
        p = f"{path_prefix}.{c.kind}"
        if p in add_paths:
            await conn.execute(
                "INSERT INTO properties_constraints"
                " (property_def_ref, kind, value, message) VALUES ($1, $2, $3, $4)",
                prop_id,
                c.kind,
                c.value,
                c.message,
            )


async def _write_allowed_values(
    conn: asyncpg.Connection,
    prop_id: uuid.UUID,
    path_prefix: str,
    avs: list[AllowedValueDef],
    diff: DiffResult,
) -> None:
    add_paths = {i.path for i in diff.adds}
    soft_paths = {i.path for i in diff.soft_updates}
    for av in avs:
        p = f"{path_prefix}.{av.slug}"
        if p in add_paths:
            await conn.execute(
                "INSERT INTO properties_allowed_values"
                " (property_def_ref, slug, label, position, color) VALUES ($1, $2, $3, $4, $5)",
                prop_id,
                av.slug,
                av.label,
                av.position,
                av.color,
            )
        elif p in soft_paths:
            await conn.execute(
                "UPDATE properties_allowed_values SET label = $1"
                " WHERE property_def_ref = $2 AND slug = $3",
                av.label,
                prop_id,
                av.slug,
            )


def _topo_sort(resolved: list[ResolvedType]) -> list[ResolvedType]:
    """Tri topologique : les types sans parent ou dont le parent est déjà placé en premier."""
    slugs = {rt.slug for rt in resolved}
    result: list[ResolvedType] = []
    placed: set[str] = set()
    remaining = list(resolved)

    max_iters = len(resolved) + 1
    while remaining and max_iters > 0:
        max_iters -= 1
        next_round: list[ResolvedType] = []
        for rt in remaining:
            if rt.parent is None or rt.parent not in slugs or rt.parent in placed:
                result.append(rt)
                placed.add(rt.slug)
            else:
                next_round.append(rt)
        remaining = next_round

    result.extend(remaining)  # cycle guard — ne devrait pas arriver
    return result


async def run_import(
    pool: asyncpg.Pool,
    ws_slug: str,
    template: Template,
    *,
    dry_run: bool = False,
) -> ImportReport:
    resolved = resolve(template)

    async with pool.acquire() as conn:
        wk_row = await conn.fetchrow(
            "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
        )
        if wk_row is None:
            raise ValueError(f"workspace '{ws_slug}' introuvable")
        wk: str = str(wk_row["workspace_technical_key"])

        current_version: int | None = await _fetch_version(conn, wk, template.template)

        if current_version is not None and template.version < current_version:
            raise VersionConflictError(
                f"régression de version interdite :"
                f" version en base={current_version}, fichier={template.version}"
            )

        diff = await compute_diff(conn, wk, resolved)

        # no_op uniquement si même version ET diff réellement vide
        # (si les types ont été supprimés, diff.adds sera non vide → on réimporte)
        if current_version == template.version and not diff.adds and not diff.soft_updates:
            log.info(
                "template_import_no_op",
                workspace=ws_slug,
                template=template.template,
                version=template.version,
            )
            return ImportReport(dry_run=dry_run, no_op=True, diff=diff)

        if diff.has_conflict:
            raise ImportConflictError(diff)

        if dry_run:
            log.info(
                "template_import_dry_run",
                workspace=ws_slug,
                adds=len(diff.adds),
                soft=len(diff.soft_updates),
            )
            return ImportReport(dry_run=True, no_op=False, diff=diff)

        async with conn.transaction():
            await _write_types(conn, wk, resolved, diff)
            await conn.execute(
                """
                INSERT INTO workspace_template_import
                    (workspace_technical_key, template, version)
                VALUES ($1, $2, $3)
                ON CONFLICT (workspace_technical_key, template)
                DO UPDATE SET version = EXCLUDED.version, imported_at = now()
                """,
                wk,
                template.template,
                template.version,
            )

        log.info(
            "template_import_applied",
            workspace=ws_slug,
            template=template.template,
            version=template.version,
            adds=len(diff.adds),
        )
        return ImportReport(dry_run=False, no_op=False, diff=diff, applied=True)

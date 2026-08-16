from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.documents.changelog import log_structure_change
from docflow.documents.service import validate_scalar_value
from docflow.templates.diff import DiffResult, compute_diff
from docflow.templates.inheritance import resolve
from docflow.templates.models import AllowedValueDef, ConstraintDef, PropDef, ResolvedType, Template

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)


class VersionConflictError(Exception):
    pass


class UnresolvedTargetTypeError(ValueError):
    pass


class ConcurrentImportError(Exception):
    """Un autre import a créé les mêmes structures pendant celui-ci.

    Le diff décidé en début de transaction est devenu faux : l'import entier est
    annulé. Le rejouer produit le bon résultat (le diff verra les structures
    posées par le gagnant)."""


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


def _validate_target_types(resolved: list[ResolvedType], known_slugs: set[str]) -> None:
    """Fail-fast : chaque target_type doit résoudre à un type existant ou importé ici."""
    valid = known_slugs | {rt.slug for rt in resolved}
    for rt in resolved:
        for prop in rt.properties:
            if prop.target_type is not None and prop.target_type not in valid:
                raise UnresolvedTargetTypeError(
                    f"propriété '{rt.slug}.{prop.slug}' : target_type '{prop.target_type}'"
                    " introuvable dans le workspace ni dans ce template"
                )


async def _fetch_version(conn: asyncpg.Connection, wk: str, template_slug: str) -> int | None:
    return await conn.fetchval(  # type: ignore[no-any-return]
        "SELECT version FROM workspace_template_import"
        " WHERE workspace_technical_key = $1 AND template = $2",
        wk,
        template_slug,
    )


async def _record_import(
    conn: asyncpg.Connection, wk: str, template_slug: str, version: int
) -> bool:
    """Enregistre la version importée ; renvoie False si une version plus récente
    est déjà enregistrée.

    La garde `WHERE ... version <= EXCLUDED.version` est le dernier rempart
    contre la régression : deux imports concurrents sérialisés par le verrou de
    ligne réévaluent la condition sur la valeur committée par le gagnant, donc
    le plus ancien ne peut pas rétrograder la version."""
    status = await conn.execute(
        """
        INSERT INTO workspace_template_import
            (workspace_technical_key, template, version)
        VALUES ($1, $2, $3)
        ON CONFLICT (workspace_technical_key, template)
        DO UPDATE SET version = EXCLUDED.version, imported_at = now()
        WHERE workspace_template_import.version <= EXCLUDED.version
        """,
        wk,
        template_slug,
        version,
    )
    return not status.endswith(" 0")


async def _stamp_provenance(
    conn: asyncpg.Connection, wk: str, template_slug: str, type_slugs: list[str]
) -> None:
    """Réconcilie la provenance : les types que ce template définit et qui n'en
    ont pas encore (import antérieur à la colonne source_template, ou type créé
    à la main puis adopté par le template) sont estampillés. Idempotent."""
    await conn.execute(
        "UPDATE functional_type SET source_template = $1"
        " WHERE workspace_technical_key = $2 AND slug = ANY($3::text[])"
        " AND source_template IS NULL",
        template_slug,
        wk,
        type_slugs,
    )


async def _write_types(
    conn: asyncpg.Connection,
    wk: str,
    template_slug: str,
    resolved: list[ResolvedType],
    diff: DiffResult,
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
                INSERT INTO functional_type
                    (slug, label, parent, workspace_technical_key, source_template,
                     content_template)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                rt.slug,
                rt.label,
                parent_id,
                wk,
                template_slug,
                rt.content_template,
            )
            assert row is not None
            slug_to_id[rt.slug] = row["id"]
        elif rt.slug in soft_paths:
            # COALESCE : un template muet sur content_template n'en gère pas la
            # valeur — il ne doit pas effacer celle posée en base (réconciliation
            # additive : une suppression est toujours explicite).
            await conn.execute(
                "UPDATE functional_type"
                " SET label = $1, source_template = $2,"
                " content_template = COALESCE($3, content_template), updated_at = now()"
                " WHERE workspace_technical_key = $4 AND slug = $5",
                rt.label,
                template_slug,
                rt.content_template,
                wk,
                rt.slug,
            )

    # Propriétés
    for rt in ordered:
        type_id = slug_to_id.get(rt.slug)
        if type_id is None:
            continue
        await _write_props(conn, type_id, rt.slug, rt.properties, diff, slug_to_id)


async def _validate_prop_default(prop: PropDef, type_slug: str) -> None:
    """Refuse (422) un `default` de template incompatible avec le type déclaré.

    Même garde que `properties.service._check_default_value` sur le chemin API :
    un défaut non castable est matérialisé sur chaque document créé et casse
    ensuite tout tri/filtre du bloc. Ici le template porte `allowed_values`, donc
    le défaut d'une restricted_list est vérifiable dès l'import.
    """
    if prop.default is None:
        return
    label = f"{type_slug}.{prop.slug}"
    if prop.type == "restricted_list":
        slugs = [av.slug for av in prop.allowed_values]
        if slugs and prop.default not in slugs:
            raise UnresolvedTargetTypeError(
                f"default '{prop.default}' de '{label}' n'est pas une valeur autorisée"
                f" ; valeurs déclarées : {', '.join(slugs)}"
            )
        return
    if prop.type == "reference":
        try:
            uuid.UUID(prop.default)
        except ValueError as exc:
            raise UnresolvedTargetTypeError(
                f"default de '{label}' (type reference) : '{prop.default}' n'est pas un UUID valide"
            ) from exc
        return
    try:
        await validate_scalar_value(prop.type, prop.default, label)
    except HTTPException as exc:
        raise UnresolvedTargetTypeError(f"default invalide : {exc.detail}") from exc


async def _write_props(
    conn: asyncpg.Connection,
    type_id: uuid.UUID,
    type_slug: str,
    props: list[PropDef],
    diff: DiffResult,
    slug_to_id: dict[str, uuid.UUID],
) -> None:
    add_paths = {i.path for i in diff.adds}
    soft_paths = {i.path for i in diff.soft_updates}

    for prop in props:
        prop_path = f"{type_slug}.{prop.slug}"
        prop_id: uuid.UUID | None = None

        if prop_path in add_paths:
            await _validate_prop_default(prop, type_slug)
            target_id = slug_to_id.get(prop.target_type) if prop.target_type else None
            row = await conn.fetchrow(
                """
                INSERT INTO properties_defs
                    (slug, label, functional_type_ref, type, default_value, required,
                     target_functional_type_ref, behavior)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                prop.slug,
                prop.label,
                type_id,
                prop.type,
                prop.default,
                prop.required,
                target_id,
                prop.behavior,
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

        # Lecture de version, décision et écriture dans la MÊME transaction :
        # sinon deux imports concurrents lisent le même état, passent tous deux
        # le contrôle de régression et le dernier committé fait foi.
        async with conn.transaction():
            report = await _run_import_tx(conn, wk, ws_slug, template, resolved, dry_run=dry_run)

    if report.no_op:
        log.info(
            "template_import_no_op",
            workspace=ws_slug,
            template=template.template,
            version=template.version,
        )
    elif report.dry_run:
        log.info(
            "template_import_dry_run",
            workspace=ws_slug,
            adds=len(report.diff.adds),
            soft=len(report.diff.soft_updates),
        )
    else:
        log.info(
            "template_import_applied",
            workspace=ws_slug,
            template=template.template,
            version=template.version,
            adds=len(report.diff.adds),
        )
    return report


async def _run_import_tx(
    conn: asyncpg.Connection,
    wk: str,
    ws_slug: str,
    template: Template,
    resolved: list[ResolvedType],
    *,
    dry_run: bool,
) -> ImportReport:
    current_version: int | None = await _fetch_version(conn, wk, template.template)

    if current_version is not None and template.version < current_version:
        raise VersionConflictError(
            f"régression de version interdite :"
            f" version en base={current_version}, fichier={template.version}"
        )

    known_slugs = {
        row["slug"]
        for row in await conn.fetch(
            "SELECT slug FROM functional_type WHERE workspace_technical_key = $1", wk
        )
    }
    _validate_target_types(resolved, known_slugs)

    diff = await compute_diff(conn, wk, resolved)
    type_slugs = [rt.slug for rt in resolved]

    # no_op uniquement si même version ET diff réellement vide
    # (si les types ont été supprimés, diff.adds sera non vide → on réimporte)
    if current_version == template.version and not diff.adds and not diff.soft_updates:
        if not dry_run:
            # Réconciliation métadonnée (pas un changement de structure) :
            # les imports antérieurs à la colonne source_template n'ont pas
            # de provenance — l'estampiller même quand l'import est no_op.
            await _stamp_provenance(conn, wk, template.template, type_slugs)
        return ImportReport(dry_run=dry_run, no_op=True, diff=diff)

    if diff.has_conflict:
        raise ImportConflictError(diff)

    if dry_run:
        return ImportReport(dry_run=True, no_op=False, diff=diff)

    try:
        await _write_types(conn, wk, template.template, resolved, diff)
    except asyncpg.UniqueViolationError as e:
        raise ConcurrentImportError(
            f"import concurrent du template '{template.template}' sur le workspace"
            f" '{ws_slug}' : structures déjà créées, rejouer l'import"
        ) from e
    # Types du template inchangés par ce diff mais sans provenance
    # (données antérieures à la colonne source_template).
    await _stamp_provenance(conn, wk, template.template, type_slugs)
    # Une seule entrée feed par import : signal d'invalidation globale
    # (types/propriétés créés par _write_types en SQL direct).
    await log_structure_change(conn, uuid.UUID(wk), "template", "U")

    if not await _record_import(conn, wk, template.template, template.version):
        raise VersionConflictError(
            "régression de version interdite : un import concurrent a enregistré"
            f" une version plus récente que {template.version}"
        )

    return ImportReport(dry_run=False, no_op=False, diff=diff, applied=True)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import asyncpg

from docflow.templates.models import AllowedValueDef, ConstraintDef, PropDef, ResolvedType

DiffKind = Literal["add", "no-op", "soft_update", "conflict"]


@dataclass
class DiffItem:
    kind: DiffKind
    path: str  # ex. "epic", "epic.statut", "epic.statut.todo"
    detail: str = ""


@dataclass
class DiffResult:
    items: list[DiffItem] = field(default_factory=list)

    @property
    def has_conflict(self) -> bool:
        return any(i.kind == "conflict" for i in self.items)

    @property
    def adds(self) -> list[DiffItem]:
        return [i for i in self.items if i.kind == "add"]

    @property
    def soft_updates(self) -> list[DiffItem]:
        return [i for i in self.items if i.kind == "soft_update"]

    @property
    def conflicts(self) -> list[DiffItem]:
        return [i for i in self.items if i.kind == "conflict"]


# ── Helpers de comparaison ─────────────────────────────────────────────────


def _diff_constraints(
    path: str,
    template: list[ConstraintDef],
    db: list[ConstraintDef],
    result: DiffResult,
) -> None:
    db_by_kind = {c.kind: c for c in db}
    for tc in template:
        if tc.kind not in db_by_kind:
            result.items.append(DiffItem(kind="add", path=f"{path}.{tc.kind}"))
        else:
            dc = db_by_kind[tc.kind]
            if dc.value != tc.value or dc.message != tc.message:
                result.items.append(
                    DiffItem(
                        kind="conflict",
                        path=f"{path}.{tc.kind}",
                        detail="contrainte modifiée (valeur ou message)",
                    )
                )
            else:
                result.items.append(DiffItem(kind="no-op", path=f"{path}.{tc.kind}"))


def _diff_allowed_values(
    path: str,
    template: list[AllowedValueDef],
    db: list[AllowedValueDef],
    result: DiffResult,
) -> None:
    db_by_slug = {av.slug: av for av in db}
    for tav in template:
        p = f"{path}.{tav.slug}"
        if tav.slug not in db_by_slug:
            result.items.append(DiffItem(kind="add", path=p))
        else:
            dav = db_by_slug[tav.slug]
            struct_changed = dav.position != tav.position or dav.color != tav.color
            label_changed = dav.label != tav.label
            if struct_changed:
                result.items.append(
                    DiffItem(kind="conflict", path=p, detail="position ou couleur modifiée")
                )
            elif label_changed:
                result.items.append(DiffItem(kind="soft_update", path=p))
            else:
                result.items.append(DiffItem(kind="no-op", path=p))


def _diff_prop(
    type_path: str,
    tp: PropDef,
    db_prop: PropDef | None,
    result: DiffResult,
) -> None:
    path = f"{type_path}.{tp.slug}"
    if db_prop is None:
        result.items.append(DiffItem(kind="add", path=path))
        for c in tp.constraints:
            result.items.append(DiffItem(kind="add", path=f"{path}.{c.kind}"))
        for av in tp.allowed_values:
            result.items.append(DiffItem(kind="add", path=f"{path}#av.{av.slug}"))
        return

    if db_prop.type != tp.type:
        result.items.append(DiffItem(kind="conflict", path=path, detail="type modifié"))
        return

    if db_prop.required != tp.required or db_prop.default != tp.default:
        result.items.append(
            DiffItem(kind="conflict", path=path, detail="required ou default modifié")
        )
        return

    label_changed = db_prop.label != tp.label
    if label_changed:
        result.items.append(DiffItem(kind="soft_update", path=path))
    else:
        result.items.append(DiffItem(kind="no-op", path=path))

    _diff_constraints(path, tp.constraints, db_prop.constraints, result)
    _diff_allowed_values(f"{path}#av", tp.allowed_values, db_prop.allowed_values, result)


# ── Snapshot DB ────────────────────────────────────────────────────────────


async def _fetch_db_snapshot(conn: asyncpg.Connection, wk: str) -> dict[str, ResolvedType]:
    """Charge la structure existante du workspace sous forme de ResolvedType."""
    rows = await conn.fetch(
        """
        SELECT ft.id, ft.slug, ft.label,
               p.slug AS parent_slug
        FROM functional_type ft
        LEFT JOIN functional_type p ON p.id = ft.parent
        WHERE ft.workspace_technical_key = $1
        """,
        wk,
    )
    snapshot: dict[str, ResolvedType] = {}
    for r in rows:
        pd_rows = await conn.fetch(
            "SELECT id, slug, label, type, default_value, required"
            " FROM properties_defs WHERE functional_type_ref = $1",
            r["id"],
        )
        props: list[PropDef] = []
        for pd in pd_rows:
            c_rows = await conn.fetch(
                "SELECT kind, value, message FROM properties_constraints"
                " WHERE property_def_ref = $1",
                pd["id"],
            )
            av_rows = await conn.fetch(
                "SELECT slug, label, position, color FROM properties_allowed_values"
                " WHERE property_def_ref = $1 ORDER BY position",
                pd["id"],
            )
            props.append(
                PropDef(
                    slug=pd["slug"],
                    label=pd["label"],
                    type=pd["type"],
                    required=pd["required"],
                    default=pd["default_value"],
                    constraints=[
                        ConstraintDef(kind=c["kind"], value=c["value"], message=c["message"])
                        for c in c_rows
                    ],
                    allowed_values=[
                        AllowedValueDef(
                            slug=av["slug"],
                            label=av["label"],
                            position=av["position"],
                            color=av["color"],
                        )
                        for av in av_rows
                    ],
                )
            )
        snapshot[r["slug"]] = ResolvedType(
            slug=r["slug"],
            label=r["label"],
            parent=r["parent_slug"],
            properties=props,
        )
    return snapshot


# ── Point d'entrée ─────────────────────────────────────────────────────────


async def compute_diff(
    conn: asyncpg.Connection,
    wk: str,
    resolved: list[ResolvedType],
) -> DiffResult:
    db_snapshot = await _fetch_db_snapshot(conn, wk)
    result = DiffResult()

    for rt in resolved:
        path = rt.slug
        db_type = db_snapshot.get(rt.slug)

        if db_type is None:
            result.items.append(DiffItem(kind="add", path=path))
            for prop in rt.properties:
                result.items.append(DiffItem(kind="add", path=f"{path}.{prop.slug}"))
                for c in prop.constraints:
                    result.items.append(DiffItem(kind="add", path=f"{path}.{prop.slug}.{c.kind}"))
                for av in prop.allowed_values:
                    result.items.append(
                        DiffItem(kind="add", path=f"{path}.{prop.slug}#av.{av.slug}")
                    )
            continue

        if db_type.parent != rt.parent:
            result.items.append(
                DiffItem(
                    kind="conflict",
                    path=path,
                    detail=f"parent modifié ({db_type.parent!r} → {rt.parent!r})",
                )
            )
            continue

        if db_type.label != rt.label:
            result.items.append(DiffItem(kind="soft_update", path=path))
        else:
            result.items.append(DiffItem(kind="no-op", path=path))

        db_props = {p.slug: p for p in db_type.properties}
        for prop in rt.properties:
            _diff_prop(path, prop, db_props.get(prop.slug), result)

    return result

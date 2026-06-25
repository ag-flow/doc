from __future__ import annotations

from docflow.templates.models import PropDef, ResolvedType, Template, TypeDef


class InheritanceCycleError(Exception):
    pass


def _merge_properties(base: list[PropDef], override: list[PropDef]) -> list[PropDef]:
    """Fusionne propriétés : override par slug = remplacement complet."""
    by_slug: dict[str, PropDef] = {p.slug: p for p in base}
    for p in override:
        by_slug[p.slug] = p
    return list(by_slug.values())


def _resolve_one(slug: str, by_slug: dict[str, TypeDef], visited: set[str]) -> list[PropDef]:
    """Résout récursivement l'héritage pour un type donné ; détecte les cycles."""
    if slug in visited:
        raise InheritanceCycleError(f"cycle d'héritage détecté impliquant '{slug}'")
    visited = visited | {slug}

    td = by_slug[slug]
    if td.inherit is None:
        return list(td.properties)

    if td.inherit not in by_slug:
        raise ValueError(
            f"type '{slug}' hérite de '{td.inherit}' qui n'existe pas dans le template"
        )

    base_props = _resolve_one(td.inherit, by_slug, visited)
    return _merge_properties(base_props, td.properties)


def resolve(template: Template) -> list[ResolvedType]:
    """
    Retourne la liste à plat des types concrets avec leurs propriétés résolues.
    Les types `abstract: true` sont exclus du résultat.
    """
    by_slug: dict[str, TypeDef] = {td.slug: td for td in template.functional_types}
    result: list[ResolvedType] = []

    for td in template.functional_types:
        if td.abstract:
            continue

        props = _resolve_one(td.slug, by_slug, set())
        result.append(ResolvedType(
            slug=td.slug,
            label=td.label if td.label is not None else td.slug,
            parent=td.parent,
            properties=props,
        ))

    return result

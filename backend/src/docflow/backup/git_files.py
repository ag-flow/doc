"""Fonctions pures de sérialisation et de réconciliation fichiers du git_sync.

Aucune I/O réseau ni DB ici : uniquement du calcul de chemins et des écritures
disque locales — testable sans infrastructure.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

SLUG_SAFE = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")


def write_doc(
    base: pathlib.Path, path_parts: list[str], doc: dict[str, Any]
) -> tuple[pathlib.Path, pathlib.Path]:
    """Écrit {slug}.md et {slug}.json dans l'arborescence et retourne les deux chemins."""
    slug = path_parts[-1]
    # Si la liste a des enfants potentiels, le répertoire parent est path_parts[:-1]
    dir_path = base.joinpath(*path_parts[:-1])
    dir_path.mkdir(parents=True, exist_ok=True)

    md_path = dir_path / f"{slug}.md"
    json_path = dir_path / f"{slug}.json"

    md_path.write_text(str(doc.get("content") or ""), encoding="utf-8")
    meta = {
        "title": doc["title"],
        "functional_type": doc.get("functional_type_slug"),
        "updated_at": str(doc["updated_at"]),
        "properties": doc.get("properties", {}),
    }
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def expected_file_paths(workspace_slug: str, docs: list[dict[str, Any]]) -> set[str]:
    """Chemins relatifs POSIX attendus (.md/.json) de TOUS les documents du workspace.

    Les slugs ne sont uniques que par fratrie (cf. 0030_document_slug.sql) :
    la réconciliation doit matcher par chemin complet dérivé de l'arbre,
    jamais par slug seul. Un document sans chemin calculable (slug manquant
    ou invalide sur lui-même ou un ancêtre, parent introuvable, cycle) n'a
    aucun chemin attendu — comme à l'export (`_build_path`).
    """
    by_id = {d["id"]: d for d in docs}
    expected: set[str] = set()
    for doc in docs:
        # Préfixe de blocs du document (None = chaîne de blocs invalide → skip,
        # même règle qu'à l'export ; absent = pas de blocs dans le chemin).
        block_parts = doc.get("block_parts", [])
        if block_parts is None:
            continue
        parts: list[str] = []
        current: dict[str, Any] | None = doc
        seen: set[Any] = set()
        while current is not None:
            slug = current["slug"]
            if not slug or not SLUG_SAFE.match(slug) or current["id"] in seen:
                parts = []
                break
            seen.add(current["id"])
            parts.insert(0, slug)
            parent_id = current["parent"]
            current = by_id.get(parent_id) if parent_id is not None else None
            if parent_id is not None and current is None:
                parts = []  # parent hors workspace / manquant
                break
        if not parts:
            continue
        rel_dir = "/".join([workspace_slug, *block_parts, *parts[:-1]])
        expected.add(f"{rel_dir}/{parts[-1]}.md")
        expected.add(f"{rel_dir}/{parts[-1]}.json")
    return expected


def find_orphan_files(
    base: pathlib.Path, workspace_slug: str, expected_paths: set[str]
) -> list[pathlib.Path]:
    """Fichiers .md/.json/.yaml du workspace dont le chemin complet n'est plus
    attendu. Le répertoire d'un workspace exporté est entièrement géré par le
    sync (marqueur .docflow-workspace) : un _block.yaml de bloc supprimé est
    purgé comme un document orphelin."""
    orphans: list[pathlib.Path] = []
    ws_dir = base / workspace_slug
    if not ws_dir.exists():
        return orphans
    for p in sorted(ws_dir.rglob("*")):
        if not p.is_file() or p.suffix not in (".md", ".json", ".yaml"):
            continue
        if p.relative_to(base).as_posix() not in expected_paths:
            orphans.append(p)
    return orphans

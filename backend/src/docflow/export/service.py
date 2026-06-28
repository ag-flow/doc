"""Service d'export Markdown + frontmatter YAML (spec 36 — MEXP).

Projette le store en arbre de fichiers markdown sans modifier la base.
"""
from __future__ import annotations

import io
import re
import uuid
import zipfile
from collections import defaultdict

import asyncpg
import yaml

from docflow.db.helpers import require_workspace

# ── Slugification des titres ──────────────────────────────────────────────────

_UNSAFE_RE = re.compile(r"[^\w\- ]+", re.UNICODE)


def _slugify(title: str) -> str:
    """Titre → slug de chemin fichier (stable, bas de casse)."""
    s = title.strip().lower()
    s = _UNSAFE_RE.sub("", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = s.strip("-")
    return s or "sans-titre"


def _unique_path(base: str, seen: set[str], suffix: str) -> str:
    """Résout les collisions en ajoutant un suffixe court déterministe."""
    candidate = base
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    candidate = f"{base}-{suffix[:6]}"
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    i = 2
    while f"{candidate}-{i}" in seen:
        i += 1
    result = f"{candidate}-{i}"
    seen.add(result)
    return result


# ── Sérialisation YAML ────────────────────────────────────────────────────────

def _yaml_value(prop_type: str, value: str | None, allowed_label: str | None) -> object:
    """Convertit une valeur de propriété en scalaire YAML."""
    if prop_type == "restricted_list":
        return allowed_label
    if prop_type == "bool" and value is not None:
        return value == "true"
    if prop_type == "int" and value is not None:
        try:
            return int(value)
        except ValueError:
            return value
    if prop_type == "float" and value is not None:
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _build_frontmatter(
    doc_id: uuid.UUID,
    title: str,
    type_slug: str | None,
    props: list[dict[str, object]],
) -> str:
    data: dict[str, object] = {"docflow_id": str(doc_id), "title": title}
    if type_slug is not None:
        data["type"] = type_slug
    for p in props:
        raw_val = p.get("value")
        raw_lbl = p.get("allowed_label")
        v = _yaml_value(
            str(p["type"]),
            str(raw_val) if raw_val is not None else None,
            str(raw_lbl) if raw_lbl is not None else None,
        )
        if v is not None:
            data[str(p["prop_slug"])] = v
    return "---\n" + yaml.dump(data, allow_unicode=True, default_flow_style=False) + "---\n\n"


# ── Réécriture des liens ──────────────────────────────────────────────────────

_DOCFLOW_LINK_RE = re.compile(
    r"\[([^\]]*)\]\(docflow://doc/([0-9a-f-]{36})\)"
)


def _rewrite_links(content: str, in_scope: dict[uuid.UUID, str]) -> str:
    """Remplace les liens docflow:// in-scope par [[wikilink]], conserve les autres."""
    def _replace(m: re.Match[str]) -> str:
        try:
            target_id = uuid.UUID(m.group(2))
        except ValueError:
            return m.group(0)
        if target_id in in_scope:
            return f"[[{in_scope[target_id]}]]"
        return m.group(0)

    return _DOCFLOW_LINK_RE.sub(_replace, content)


# ── Projection arbre → fichiers ───────────────────────────────────────────────

async def build_export_zip(
    pool: asyncpg.Pool,
    ws_slug: str,
    bloc_slug: str | None = None,
) -> bytes:
    """Construit l'archive ZIP du workspace (ou d'un seul bloc) en mémoire."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)

        # ── Lire les blocs ───────────────────────────────────────────────────
        if bloc_slug is not None:
            bloc_rows = await conn.fetch(
                """
                SELECT db.id, db.slug
                FROM data_block db
                WHERE db.workspace_technical_key = $1 AND db.slug = $2
                """,
                wk,
                bloc_slug,
            )
        else:
            bloc_rows = await conn.fetch(
                """
                SELECT db.id, db.slug
                FROM data_block db
                WHERE db.workspace_technical_key = $1
                ORDER BY db.created_at
                """,
                wk,
            )

        # ── Lire tous les documents (avec contenu courant + type) ────────────
        doc_rows = await conn.fetch(
            """
            SELECT d.doc_technical_key AS id,
                   d.title,
                   d.parent,
                   d.data_block_ref,
                   ft.slug             AS type_slug,
                   dv.content
            FROM document d
            LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
            LEFT JOIN document_version dv
                ON dv.document_ref = d.doc_technical_key AND dv.version_number = d.version
            WHERE d.workspace_technical_key = $1
            ORDER BY d.created_at
            """,
            wk,
        )

        # ── Lire les valeurs de propriétés ───────────────────────────────────
        prop_rows = await conn.fetch(
            """
            SELECT pv.document_ref,
                   pd.slug      AS prop_slug,
                   pd.type,
                   pvv.value,
                   pav.label    AS allowed_label
            FROM properties_values pv
            JOIN properties_defs pd ON pd.id = pv.property_def_ref
            JOIN properties_value_version pvv
                ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
            LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
            WHERE pv.workspace_technical_key = $1
            ORDER BY pv.document_ref, pd.created_at
            """,
            wk,
        )

    # ── Indexation ────────────────────────────────────────────────────────────
    docs_by_id: dict[uuid.UUID, dict[str, object]] = {}
    for r in doc_rows:
        docs_by_id[r["id"]] = dict(r)

    children_of: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
    for doc_id, doc in docs_by_id.items():
        parent = doc["parent"]
        children_of[parent if isinstance(parent, uuid.UUID) else None].append(doc_id)

    props_by_doc: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(list)
    for r in prop_rows:
        props_by_doc[r["document_ref"]].append(dict(r))

    # in_scope = {doc_id: titre} pour réécriture des liens
    in_scope: dict[uuid.UUID, str] = {
        did: str(d.get("title") or "") for did, d in docs_by_id.items()
    }

    # ── Construire le ZIP ─────────────────────────────────────────────────────
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:

        def _write_doc(
            doc_id: uuid.UUID,
            folder: str,
            seen_siblings: set[str],
        ) -> None:
            doc = docs_by_id.get(doc_id)
            if doc is None:
                return
            title: str = str(doc.get("title") or "sans-titre")
            slug = _slugify(title)
            filename = _unique_path(slug, seen_siblings, str(doc_id))
            path = f"{folder}/{filename}.md"

            props = props_by_doc.get(doc_id, [])
            type_slug_raw = doc.get("type_slug")
            type_slug: str | None = str(type_slug_raw) if type_slug_raw is not None else None
            fm = _build_frontmatter(doc_id, title, type_slug, props)
            raw_content: str = str(doc.get("content") or "")
            body = _rewrite_links(raw_content, in_scope)
            zf.writestr(path, fm + body)

            child_ids = children_of.get(doc_id, [])
            if child_ids:
                child_folder = f"{folder}/{filename}"
                seen_children: set[str] = set()
                for cid in child_ids:
                    _write_doc(cid, child_folder, seen_children)

        for br in bloc_rows:
            bloc_id = br["id"]
            bloc_folder = f"{ws_slug}/{br['slug']}"
            # Racines = documents du bloc sans parent (ou avec parent hors-bloc)
            root_ids = [
                did for did in children_of.get(None, [])
                if docs_by_id.get(did, {}).get("data_block_ref") == bloc_id
            ]
            # Plus les documents du bloc avec parent hors-scope de ce bloc
            all_bloc = [did for did, d in docs_by_id.items() if d.get("data_block_ref") == bloc_id]
            bloc_set = set(all_bloc)
            root_ids = [did for did in all_bloc if docs_by_id[did]["parent"] not in bloc_set]
            seen_roots: set[str] = set()
            for rid in root_ids:
                _write_doc(rid, bloc_folder, seen_roots)

    return buf.getvalue()

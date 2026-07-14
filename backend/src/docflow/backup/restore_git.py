"""Restauration d'un miroir git_sync vers une instance docflow.

Parcourt une arborescence exportée par git_sync (`<workspace>/<blocs>/<docs>`,
cf. DEPLOY.md § « Et le miroir git ? ») et recrée ce qui manque : workspaces,
types (via l'importeur de templates, depuis les `_block.yaml`), blocs, puis
documents (contenu markdown + titre/type/propriétés du `.json`).

Restauration **additive et idempotente** : crée ce qui manque, réaligne
titre/contenu/propriétés des documents existants (matching par chemin de
slugs), ne supprime jamais rien. La reprise totale d'une instance (comptes,
secrets, historique) passe par le dump Postgres.

Usage (dans le conteneur app, après un clone du repo de sauvegarde) :

    python -m docflow.backup.restore_git /chemin/du/clone [--workspace slug]
"""

from __future__ import annotations

import json
import pathlib
import uuid
from dataclasses import dataclass, field
from typing import Any

import asyncpg
import structlog
import yaml

from docflow.backup.type_export import BLOCK_META_FILENAME
from docflow.blocks import service as block_svc
from docflow.documents import service as doc_svc
from docflow.schemas.block import DataBlockCreate
from docflow.schemas.document import DocumentCreate, DocumentUpdate
from docflow.schemas.property_value import PropertyValueSet
from docflow.schemas.workspace import WorkspaceCreate
from docflow.templates.importer import run_import
from docflow.templates.models import Template
from docflow.workspaces import service as ws_svc

log = structlog.get_logger(__name__)

_WS_MARKER = ".docflow-workspace"


@dataclass
class RestoreReport:
    workspaces_created: int = 0
    blocks_created: int = 0
    types_imported: int = 0
    docs_created: int = 0
    docs_updated: int = 0
    errors: list[str] = field(default_factory=list)


def discover_export_bases(root: pathlib.Path) -> list[pathlib.Path]:
    """Répertoires « base » d'export dans un clone : parents des répertoires de
    workspace marqués `.docflow-workspace` (déposés à la sauvegarde — le base
    path du job d'origine n'a donc pas à être resaisi à la restauration).
    Le contenu de .git est ignoré."""
    bases: set[pathlib.Path] = set()
    for marker in root.rglob(_WS_MARKER):
        if ".git" in marker.parts:
            continue
        bases.add(marker.parent.parent)
    return sorted(bases)


async def restore_tree(
    pool: asyncpg.Pool, base: pathlib.Path, only_workspace: str | None = None
) -> RestoreReport:
    """Restaure tous les workspaces marqués du répertoire `base`."""
    report = RestoreReport()
    for ws_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        if not (ws_dir / _WS_MARKER).exists():
            continue  # répertoire étranger au sync — jamais touché
        if only_workspace is not None and ws_dir.name != only_workspace:
            continue
        await _restore_workspace(pool, ws_dir, report)
    return report


async def _restore_workspace(
    pool: asyncpg.Pool, ws_dir: pathlib.Path, report: RestoreReport
) -> None:
    ws_slug = ws_dir.name
    exists = await pool.fetchval("SELECT 1 FROM workspace WHERE slug = $1", ws_slug)
    if not exists:
        await ws_svc.create_workspace(pool, WorkspaceCreate(slug=ws_slug, label=ws_slug), None)
        report.workspaces_created += 1
    for child in sorted(p for p in ws_dir.iterdir() if p.is_dir()):
        if (child / BLOCK_META_FILENAME).exists():
            await _restore_block_dir(pool, ws_slug, child, None, report)


async def _restore_block_dir(
    pool: asyncpg.Pool,
    ws_slug: str,
    block_dir: pathlib.Path,
    parent_block_slug: str | None,
    report: RestoreReport,
) -> None:
    block_slug = block_dir.name
    try:
        meta = yaml.safe_load((block_dir / BLOCK_META_FILENAME).read_text(encoding="utf-8"))
        # 1. Types du bloc — réutilise l'importeur de templates (diff additif,
        # conflits bloquants signalés plutôt qu'écrasés).
        if meta.get("functional_types"):
            tpl = Template(
                version=1,
                template=f"{block_slug}-types",
                label=f"Types du bloc {block_slug}",
                functional_types=meta["functional_types"],
            )
            result = await run_import(pool, ws_slug, tpl)
            if result.applied:
                report.types_imported += 1

        # 2. Le bloc lui-même
        wk = await pool.fetchval(
            "SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws_slug
        )
        block_id = await pool.fetchval(
            "SELECT id FROM data_block WHERE workspace_technical_key = $1 AND slug = $2",
            wk,
            block_slug,
        )
        if block_id is None:
            created = await block_svc.create_block(
                pool,
                ws_slug,
                DataBlockCreate(
                    slug=block_slug,
                    label=str(meta.get("label") or block_slug),
                    functional_type_slug=str(meta["type"]),
                    parent_slug=parent_block_slug,
                ),
            )
            block_id = created.id
            report.blocks_created += 1
    except Exception as exc:  # noqa: BLE001 — un bloc en échec n'arrête pas le reste
        report.errors.append(f"{ws_slug}/{block_slug}: {exc}")
        log.warning("restore_block_failed", workspace=ws_slug, block=block_slug, error=str(exc))
        return

    # 3. Documents du bloc, puis sous-blocs
    await _restore_docs(pool, ws_slug, block_id, block_dir, None, report)
    for child in sorted(p for p in block_dir.iterdir() if p.is_dir()):
        if (child / BLOCK_META_FILENAME).exists():
            await _restore_block_dir(pool, ws_slug, child, block_slug, report)


async def _restore_docs(
    pool: asyncpg.Pool,
    ws_slug: str,
    block_id: uuid.UUID,
    directory: pathlib.Path,
    parent_doc_id: uuid.UUID | None,
    report: RestoreReport,
) -> None:
    for md_path in sorted(directory.glob("*.md")):
        slug = md_path.stem
        try:
            doc_id = await _restore_one_doc(pool, ws_slug, block_id, md_path, parent_doc_id, report)
        except Exception as exc:  # noqa: BLE001 — continuer les autres documents
            report.errors.append(f"{ws_slug}/…/{slug}: {exc}")
            log.warning("restore_doc_failed", workspace=ws_slug, slug=slug, error=str(exc))
            continue
        child_dir = directory / slug
        if child_dir.is_dir() and not (child_dir / BLOCK_META_FILENAME).exists():
            await _restore_docs(pool, ws_slug, block_id, child_dir, doc_id, report)


async def _restore_one_doc(
    pool: asyncpg.Pool,
    ws_slug: str,
    block_id: uuid.UUID,
    md_path: pathlib.Path,
    parent_doc_id: uuid.UUID | None,
    report: RestoreReport,
) -> uuid.UUID:
    slug = md_path.stem
    content = md_path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    json_path = md_path.with_suffix(".json")
    if json_path.exists():
        meta = json.loads(json_path.read_text(encoding="utf-8"))
    title = str(meta.get("title") or slug)
    type_slug = meta.get("functional_type")
    properties = {str(k): str(v) for k, v in (meta.get("properties") or {}).items()}

    row = await pool.fetchrow(
        """
        SELECT d.doc_technical_key AS id, d.version, d.title, dv.content
        FROM document d
        LEFT JOIN document_version dv
               ON dv.document_ref = d.doc_technical_key AND dv.version_number = d.version
        WHERE d.data_block_ref = $1 AND d.slug = $2 AND d.parent IS NOT DISTINCT FROM $3
        """,
        block_id,
        slug,
        parent_doc_id,
    )
    if row is None:
        created = await doc_svc.create_document(
            pool,
            ws_slug,
            DocumentCreate(
                title=title,
                block_id=block_id,
                slug=slug,
                content=content,
                parent_id=parent_doc_id,
                functional_type_slug=str(type_slug) if type_slug else None,
                properties=properties or None,
            ),
        )
        report.docs_created += 1
        return created.doc_technical_key

    doc_id: uuid.UUID = row["id"]
    if row["title"] != title or (row["content"] or "") != content:
        await doc_svc.update_document(
            pool,
            ws_slug,
            doc_id,
            DocumentUpdate(title=title, content=content, expected_version=row["version"]),
        )
        report.docs_updated += 1
    for prop_slug, value in properties.items():
        await _set_property(pool, ws_slug, doc_id, prop_slug, value)
    return doc_id


async def _set_property(
    pool: asyncpg.Pool, ws_slug: str, doc_id: uuid.UUID, prop_slug: str, value: str
) -> None:
    """Réaligne une valeur de propriété (no-op si identique)."""
    current = await pool.fetchrow(
        """
        SELECT pv.version, pvv.value, pav.slug AS av_slug, pd.type
        FROM properties_defs pd
        JOIN document d ON d.functional_type_ref = pd.functional_type_ref
        LEFT JOIN properties_values pv
               ON pv.property_def_ref = pd.id AND pv.document_ref = d.doc_technical_key
        LEFT JOIN properties_value_version pvv
               ON pvv.property_value_ref = pv.id AND pvv.version_number = pv.version
        LEFT JOIN properties_allowed_values pav ON pav.id = pvv.allowed_value_ref
        WHERE d.doc_technical_key = $1 AND pd.slug = $2
        """,
        doc_id,
        prop_slug,
    )
    if current is None:
        return  # propriété inconnue du type — signalée par l'import des types
    existing = current["av_slug"] if current["type"] == "restricted_list" else current["value"]
    if existing == value:
        return
    body = (
        PropertyValueSet(allowed_value_slug=value, expected_version=current["version"] or 0)
        if current["type"] == "restricted_list"
        else PropertyValueSet(value=value, expected_version=current["version"] or 0)
    )
    await doc_svc.set_property_value(pool, ws_slug, doc_id, prop_slug, body)

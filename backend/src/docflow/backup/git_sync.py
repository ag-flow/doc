from __future__ import annotations

import json
import pathlib
import re
import shutil
import tempfile
import uuid
from typing import Any

import asyncpg
import structlog
from git import GitCommandError, InvalidGitRepositoryError, Repo

log = structlog.get_logger(__name__)

_SLUG_SAFE = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")


# ── Sérialisation d'un document ───────────────────────────────────────────────

async def _fetch_doc(
    conn: asyncpg.Connection, doc_id: uuid.UUID
) -> dict[str, Any] | None:
    """Retourne les données brutes d'un document avec son contenu et ses propriétés."""
    row = await conn.fetchrow(
        """
        SELECT d.doc_technical_key AS id, d.slug, d.title, d.updated_at,
               d.parent AS parent_id,
               d.workspace_technical_key AS workspace_id,
               ft.slug AS functional_type_slug,
               dv.content
        FROM document d
        LEFT JOIN functional_type ft ON ft.id = d.functional_type_ref
        LEFT JOIN document_version dv
               ON dv.document_ref = d.doc_technical_key
              AND dv.version_number = d.version
        WHERE d.doc_technical_key = $1
        """,
        doc_id,
    )
    if row is None:
        return None
    doc = dict(row)

    prop_rows = await conn.fetch(
        """
        SELECT pd.slug AS prop_slug, pd.type AS prop_type,
               pvv.value, pvv.allowed_value_ref
        FROM properties_values pv
        JOIN properties_defs pd ON pd.id = pv.property_def_ref
        JOIN properties_value_version pvv
               ON pvv.property_value_ref = pv.id
              AND pvv.version_number = pv.version
        WHERE pv.document_ref = $1
        ORDER BY pd.slug
        """,
        doc_id,
    )
    doc["properties"] = {r["prop_slug"]: r["value"] or r["allowed_value_ref"] for r in prop_rows}
    return doc


async def _build_path(
    conn: asyncpg.Connection,
    doc_id: uuid.UUID,
    workspace_slug: str,
) -> list[str] | None:
    """Remonte l'arborescence et retourne la liste de slugs [racine, ..., doc].
    Retourne None si un ancêtre n'a pas de slug (skip ce document)."""
    parts: list[str] = []
    current_id: uuid.UUID | None = doc_id
    while current_id is not None:
        row = await conn.fetchrow(
            "SELECT slug, parent FROM document WHERE doc_technical_key = $1",
            current_id,
        )
        if row is None:
            return None
        slug = row["slug"]
        if not slug or not _SLUG_SAFE.match(slug):
            return None  # document sans slug → skip
        parts.insert(0, slug)
        current_id = row["parent"]
    # Préfixe workspace
    parts.insert(0, workspace_slug)
    return parts


def _write_doc(
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


# ── Réconciliation des suppressions ──────────────────────────────────────────

async def _current_doc_slugs(
    conn: asyncpg.Connection, workspace_id: uuid.UUID
) -> set[str]:
    """Retourne tous les slugs de documents existants dans le workspace."""
    rows = await conn.fetch(
        "SELECT slug FROM document WHERE workspace_technical_key = $1 AND slug IS NOT NULL",
        workspace_id,
    )
    return {r["slug"] for r in rows}


def _find_orphan_files(
    repo_dir: pathlib.Path, workspace_slug: str, existing_slugs: set[str]
) -> list[pathlib.Path]:
    """Retourne les fichiers .md/.json dont le slug parent ne correspond à aucun doc actif."""
    orphans: list[pathlib.Path] = []
    ws_dir = repo_dir / workspace_slug
    if not ws_dir.exists():
        return orphans
    for p in ws_dir.rglob("*.md"):
        slug = p.stem
        if slug not in existing_slugs:
            orphans.append(p)
            json_p = p.with_suffix(".json")
            if json_p.exists():
                orphans.append(json_p)
    return orphans


# ── Entrée principale ─────────────────────────────────────────────────────────

async def run_git_sync(
    pool: asyncpg.Pool,
    *,
    job_id: uuid.UUID,
    workspace_technical_key: uuid.UUID | None,
    workspace_slug: str | None,
    last_change_seq: int,
    remote_url: str,
    git_branch: str,
    git_base_path: str | None,
    ssh_key_path: str | None,
    repos_root: pathlib.Path,
) -> dict[str, Any]:
    """
    Exécute une synchronisation git incrémentale.

    Retourne {"last_change_seq", "files_written", "files_deleted", "commit_sha"}.
    Lève une exception en cas d'erreur — le caller gère le run_status.
    """
    async with pool.acquire() as conn:
        # 1. Changements depuis le dernier run
        where_ws = (
            "AND workspace_technical_key = $2" if workspace_technical_key else ""
        )
        params: list[Any] = [last_change_seq]
        if workspace_technical_key:
            params.append(workspace_technical_key)
        change_rows = await conn.fetch(
            f"""
            SELECT seq, document_ref, nature, workspace_technical_key AS ws_id
            FROM document_change_log
            WHERE seq > $1 {where_ws}
            ORDER BY seq
            """,
            *params,
        )

        if not change_rows:
            log.info("git_sync_no_changes", job_id=str(job_id))
            return {
                "last_change_seq": last_change_seq,
                "files_written": 0,
                "files_deleted": 0,
                "commit_sha": None,
            }

        new_seq = change_rows[-1]["seq"]

        # 2. Fetch les docs C/U
        to_write: list[tuple[list[str], dict[str, Any]]] = []
        for row in change_rows:
            if row["nature"] in ("C", "U", "P"):
                ws_slug = workspace_slug or await conn.fetchval(
                    "SELECT slug FROM workspace WHERE workspace_technical_key = $1",
                    row["ws_id"],
                )
                if not ws_slug:
                    continue
                doc = await _fetch_doc(conn, row["document_ref"])
                if doc is None:
                    continue  # supprimé entre-temps — géré par reconciliation
                path_parts = await _build_path(conn, row["document_ref"], ws_slug)
                if path_parts is None:
                    log.warning("git_sync_skip_no_slug", doc_id=str(row["document_ref"]))
                    continue
                to_write.append((path_parts, doc))

        # 3. Slugs actuels pour réconciliation des suppressions
        ws_ids: set[uuid.UUID] = {row["ws_id"] for row in change_rows}
        existing_slugs: set[str] = set()
        for ws_id in ws_ids:
            existing_slugs |= await _current_doc_slugs(conn, ws_id)

    # 4. Préparer le répertoire git local
    repo_dir = repos_root / str(job_id)
    env = {}
    if ssh_key_path:
        env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no"

    try:
        try:
            repo = Repo(repo_dir)
            repo.git.update_environment(**env)
            repo.remotes.origin.pull(git_branch, ff_only=True)
        except (InvalidGitRepositoryError, Exception):
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            repo_dir.mkdir(parents=True)
            repo = Repo.clone_from(
                remote_url, repo_dir,
                branch=git_branch,
                env=env,
            )
    except GitCommandError as e:
        raise RuntimeError(f"git clone/pull échoué : {e}") from e

    base = repo_dir / git_base_path if git_base_path else repo_dir

    # 5. Écrire les fichiers modifiés
    files_written = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_base = pathlib.Path(tmp)
        for path_parts, doc in to_write:
            _write_doc(tmp_base, path_parts, doc)

        for src in tmp_base.rglob("*"):
            if src.is_file():
                rel = src.relative_to(tmp_base)
                dst = base / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                files_written += 1

    # 6. Supprimer les fichiers orphelins
    ws_slugs = {workspace_slug} if workspace_slug else {
        p.name for p in base.iterdir() if p.is_dir()
    }
    files_deleted = 0
    for ws_slug in ws_slugs:
        for orphan in _find_orphan_files(base, ws_slug, existing_slugs):
            orphan.unlink()
            files_deleted += 1

    # 7. Commit + push
    repo.git.add(A=True)
    if repo.is_dirty(untracked_files=True):
        commit = repo.index.commit(
            f"docflow sync — {files_written} écrits, {files_deleted} supprimés"
        )
        try:
            repo.remotes.origin.push(git_branch, env=env)
        except GitCommandError as e:
            raise RuntimeError(f"git push échoué : {e}") from e
        commit_sha = commit.hexsha[:12]
    else:
        commit_sha = None

    return {
        "last_change_seq": new_seq,
        "files_written": files_written,
        "files_deleted": files_deleted,
        "commit_sha": commit_sha,
    }

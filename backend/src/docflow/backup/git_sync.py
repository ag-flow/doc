from __future__ import annotations

import asyncio
import pathlib
import shutil
import tempfile
import uuid
from typing import Any

import asyncpg
import structlog
from git import GitCommandError, InvalidGitRepositoryError, Repo

from docflow.backup.git_files import expected_file_paths, find_orphan_files, write_doc
from docflow.backup.git_queries import build_path, fetch_doc, fetch_ws_documents

log = structlog.get_logger(__name__)


# ── Phase git bloquante ───────────────────────────────────────────────────────


def _git_phase(
    *,
    repo_dir: pathlib.Path,
    remote_url: str,
    git_branch: str,
    git_base_path: str | None,
    ssh_key_path: str | None,
    git_http_env: dict[str, str],
    to_write: list[tuple[list[str], dict[str, Any]]],
    reconcile: dict[str, set[str]],
) -> tuple[int, int, str | None]:
    """Phase git purement bloquante : clone/pull, écritures disque, commit, push.

    Aucune I/O DB ici — à exécuter via `asyncio.to_thread`, jamais dans le
    loop principal. Retourne (files_written, files_deleted, commit_sha|None).

    `reconcile` : workspace_slug → ensemble des chemins relatifs attendus.
    Seuls ces workspaces sont réconciliés — un workspace hors du batch n'est
    JAMAIS touché.
    """
    # 4. Préparer le répertoire git local.
    # `env` porte l'authentification hors de l'URL et de l'argv persistant :
    #   - SSH : GIT_SSH_COMMAND pointe sur la clé privée temporaire ;
    #   - PAT HTTPS : en-tête Authorization via GIT_CONFIG_* (git_http_env),
    #     jamais écrit dans `.git/config`.
    # GIT_TERMINAL_PROMPT=0 : échec propre plutôt qu'un prompt bloquant si
    # l'auth ne passe pas.
    env: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0"}
    env.update(git_http_env)
    if ssh_key_path:
        env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no"

    try:
        try:
            repo = Repo(repo_dir)
            repo.git.update_environment(**env)
            # L'URL du remote ne doit jamais contenir de secret : on la réaligne
            # sur l'URL sans credentials (scrub d'un éventuel remote hérité).
            repo.remotes.origin.set_url(remote_url)
            repo.remotes.origin.pull(git_branch, ff_only=True)
        except (InvalidGitRepositoryError, Exception):
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            repo_dir.mkdir(parents=True)
            repo = Repo.clone_from(
                remote_url,
                repo_dir,
                branch=git_branch,
                env=env,
            )
            repo.git.update_environment(**env)
    except GitCommandError as e:
        raise RuntimeError(f"git clone/pull échoué : {e}") from e

    base = repo_dir / git_base_path if git_base_path else repo_dir

    # 5. Écrire les fichiers modifiés
    files_written = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_base = pathlib.Path(tmp)
        for path_parts, doc in to_write:
            write_doc(tmp_base, path_parts, doc)

        for src in tmp_base.rglob("*"):
            if src.is_file():
                rel = src.relative_to(tmp_base)
                dst = base / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                files_written += 1

    # 6. Supprimer les fichiers orphelins — réconciliation par chemin complet,
    # strictement restreinte aux workspaces couverts par le batch.
    files_deleted = 0
    for ws_slug, expected_paths in reconcile.items():
        for orphan in find_orphan_files(base, ws_slug, expected_paths):
            orphan.unlink()
            files_deleted += 1

    # 7. Commit + push
    repo.git.add(A=True)
    if repo.is_dirty(untracked_files=True):
        commit = repo.index.commit(
            f"docflow sync — {files_written} écrits, {files_deleted} supprimés"
        )
        try:
            repo.remotes.origin.push(git_branch)
        except GitCommandError as e:
            raise RuntimeError(f"git push échoué : {e}") from e
        commit_sha = commit.hexsha[:12]
    else:
        commit_sha = None

    return files_written, files_deleted, commit_sha


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
    git_http_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Exécute une synchronisation git incrémentale en deux phases :

    - phase DB **async**, exécutée dans le loop principal (le pool asyncpg est
      lié à son event loop : jamais d'accès depuis un autre loop/thread) ;
    - phase git **bloquante** (`_git_phase`) déportée via `asyncio.to_thread`.

    Retourne {"last_change_seq", "files_written", "files_deleted", "commit_sha"}.
    Lève une exception en cas d'erreur — le caller gère le run_status.
    """
    async with pool.acquire() as conn:
        # 1. Changements depuis le dernier run
        where_ws = "AND workspace_technical_key = $2" if workspace_technical_key else ""
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
                doc = await fetch_doc(conn, row["document_ref"])
                if doc is None:
                    continue  # supprimé entre-temps — géré par reconciliation
                path_parts = await build_path(conn, row["document_ref"], ws_slug)
                if path_parts is None:
                    log.warning("git_sync_skip_no_slug", doc_id=str(row["document_ref"]))
                    continue
                to_write.append((path_parts, doc))

        # 3. Chemins attendus pour la réconciliation des suppressions.
        # Périmètre = uniquement les workspaces présents dans le batch : un
        # workspace sans changement n'apparaît pas ici et ne sera pas touché.
        reconcile: dict[str, set[str]] = {}
        for ws_id in {row["ws_id"] for row in change_rows}:
            ws_slug = workspace_slug or await conn.fetchval(
                "SELECT slug FROM workspace WHERE workspace_technical_key = $1",
                ws_id,
            )
            if not ws_slug:
                continue  # workspace introuvable → ne rien purger
            docs = await fetch_ws_documents(conn, ws_id)
            reconcile[ws_slug] = expected_file_paths(ws_slug, docs)

    # Phases 4-7 : purement bloquantes (git + disque), hors du loop principal.
    files_written, files_deleted, commit_sha = await asyncio.to_thread(
        _git_phase,
        repo_dir=repos_root / str(job_id),
        remote_url=remote_url,
        git_branch=git_branch,
        git_base_path=git_base_path,
        ssh_key_path=ssh_key_path,
        git_http_env=git_http_env or {},
        to_write=to_write,
        reconcile=reconcile,
    )

    return {
        "last_change_seq": new_seq,
        "files_written": files_written,
        "files_deleted": files_deleted,
        "commit_sha": commit_sha,
    }

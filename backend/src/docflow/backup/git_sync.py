from __future__ import annotations

import asyncio
import pathlib
import shutil
import tempfile
import uuid
from typing import Any

import asyncpg
import structlog
from git import Git, GitCommandError, InvalidGitRepositoryError, Repo

from docflow.backup.git_files import find_orphan_files, write_doc
from docflow.backup.git_queries import (
    collect_full_export,
    collect_incremental,
    resolve_block_scope,
)

log = structlog.get_logger(__name__)

# Marqueur déposé à la racine de chaque répertoire de workspace exporté :
# la purge d'un workspace supprimé ne touche QUE les répertoires marqués —
# un contenu étranger présent dans le repo n'est jamais détruit.
_WS_MARKER = ".docflow-workspace"


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
    live_workspace_slugs: set[str] | None = None,
    extra_files: list[tuple[list[str], str]] | None = None,
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

    # 5bis. Fichiers annexes (métadonnées de blocs `_block.yaml`) — contenu
    # fourni par la phase DB, écrit tel quel.
    for path_parts, content in extra_files or []:
        dst = base.joinpath(*path_parts)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        files_written += 1

    # 6. Supprimer les fichiers orphelins — réconciliation par chemin complet,
    # strictement restreinte aux workspaces couverts par le batch.
    files_deleted = 0
    for ws_slug, expected_paths in reconcile.items():
        for orphan in find_orphan_files(base, ws_slug, expected_paths):
            orphan.unlink()
            files_deleted += 1

    # 6bis. Marquer les workspaces exportés, puis purger ceux qui n'existent
    # plus côté docflow (jobs d'instance uniquement : live_workspace_slugs).
    for ws_slug in reconcile:
        ws_dir = base / ws_slug
        if ws_dir.exists():
            (ws_dir / _WS_MARKER).write_text(ws_slug, encoding="utf-8")
    if live_workspace_slugs is not None and base.exists():
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name == ".git":
                continue
            if (child / _WS_MARKER).exists() and child.name not in live_workspace_slugs:
                files_deleted += sum(
                    1
                    for p in child.rglob("*")
                    if p.is_file() and p.suffix in (".md", ".json", ".yaml")
                )
                shutil.rmtree(child)

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


def test_git_connection(
    remote_url: str, *, ssh_key_path: str | None, git_http_env: dict[str, str]
) -> None:
    """Vérifie la connectivité + authentification via `git ls-remote` (lecture seule, pas de clone).

    Bloquant — à appeler via asyncio.to_thread. Même construction d'environnement
    que `_git_phase` (secrets hors argv/URL persistante).
    """
    env: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0"}
    env.update(git_http_env)
    if ssh_key_path:
        env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no"
    git_cmd = Git()
    git_cmd.update_environment(**env)
    try:
        git_cmd.ls_remote(remote_url)
    except GitCommandError as e:
        raise RuntimeError(f"git ls-remote échoué : {e}") from e


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
    data_block_ref: uuid.UUID | None = None,
) -> dict[str, Any]:
    """
    Exécute une synchronisation git incrémentale en deux phases :

    - phase DB **async**, exécutée dans le loop principal (le pool asyncpg est
      lié à son event loop : jamais d'accès depuis un autre loop/thread) ;
    - phase git **bloquante** (`_git_phase`) déportée via `asyncio.to_thread`.

    `data_block_ref` restreint la synchronisation à un bloc et sa descendance
    (résolu une fois en `block_scope`) — None = tout le workspace, comportement
    inchangé.

    Retourne {"last_change_seq", "files_written", "files_deleted", "commit_sha"}.
    Lève une exception en cas d'erreur — le caller gère le run_status.
    """
    async with pool.acquire() as conn:
        block_scope: set[uuid.UUID] | None = None
        if data_block_ref is not None:
            block_scope = await resolve_block_scope(conn, data_block_ref)

        # 0. Jobs d'instance : liste des workspaces vivants, pour purger du
        # repo ceux qui ont été supprimés (marqueur, cf. _git_phase).
        live_ws_slugs: set[str] | None = None
        if workspace_technical_key is None:
            live_ws_slugs = {r["slug"] for r in await conn.fetch("SELECT slug FROM workspace")}

        to_write: list[tuple[list[str], dict[str, Any]]] = []
        reconcile: dict[str, set[str]] = {}
        extra_files: list[tuple[list[str], str]] = []

        if last_change_seq == 0:
            # Premier run : le journal des changements ne couvre pas forcément
            # les documents antérieurs à sa mise en place → export initial
            # complet du périmètre, curseur posé au max courant du journal.
            new_seq = await conn.fetchval("SELECT COALESCE(MAX(seq), 0) FROM document_change_log")
            to_write, reconcile, extra_files = await collect_full_export(
                conn,
                workspace_technical_key=workspace_technical_key,
                workspace_slug=workspace_slug,
                block_scope=block_scope,
            )
            log.info(
                "git_sync_initial_full_export",
                job_id=str(job_id),
                documents=len(to_write),
            )
        else:
            # 1-3. Collecte incrémentale depuis le journal des changements.
            collected = await collect_incremental(
                conn,
                workspace_technical_key=workspace_technical_key,
                workspace_slug=workspace_slug,
                last_change_seq=last_change_seq,
                block_scope=block_scope,
            )
            if collected is None:
                log.info("git_sync_no_changes", job_id=str(job_id))
                return {
                    "last_change_seq": last_change_seq,
                    "files_written": 0,
                    "files_deleted": 0,
                    "commit_sha": None,
                }
            new_seq, to_write, reconcile, extra_files = collected

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
        live_workspace_slugs=live_ws_slugs,
        extra_files=extra_files,
    )

    return {
        "last_change_seq": new_seq,
        "files_written": files_written,
        "files_deleted": files_deleted,
        "commit_sha": commit_sha,
    }

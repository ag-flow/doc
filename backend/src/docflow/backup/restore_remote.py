"""Restauration du miroir git depuis un remote point, sans accès shell.

Clone (shallow) le dépôt du remote point avec son authentification stockée
(certificat SSH ou PAT — même résolution que git_sync), puis rejoue
`restore_tree` sur l'arborescence. Le clone et la clé privée temporaire sont
détruits en fin d'opération, succès ou non.
"""

from __future__ import annotations

import asyncio
import pathlib
import shutil
import tempfile

import asyncpg
import structlog
from fastapi import HTTPException
from git import GitCommandError, Repo

from docflow.backup.restore_git import RestoreReport, restore_tree
from docflow.remote import service as rp_svc
from docflow.remote.connection import delete_key_file, resolve_git_auth

log = structlog.get_logger(__name__)


async def restore_from_remote(
    pool: asyncpg.Pool,
    settings: object,
    *,
    remote_point_slug: str,
    git_base_path: str | None = None,
    workspace: str | None = None,
) -> RestoreReport:
    point = await rp_svc.get_point(pool, remote_point_slug)
    if point.point_type != "git":
        raise HTTPException(422, "la restauration git exige un remote point de type git")

    remote_url, ssh_key_path, git_env = await resolve_git_auth(pool, remote_point_slug, settings)
    tmp = tempfile.mkdtemp(prefix="docflow-restore-")
    try:
        repo_dir = pathlib.Path(tmp) / "repo"

        def _clone() -> None:
            env: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0", **git_env}
            if ssh_key_path:
                env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no"
            Repo.clone_from(
                remote_url,
                repo_dir,
                branch=point.git_branch or "main",
                depth=1,
                env=env,
            )

        try:
            await asyncio.to_thread(_clone)
        except GitCommandError as e:
            log.warning("restore_git_clone_failed", point=remote_point_slug, error=str(e))
            raise HTTPException(502, f"clone du dépôt de sauvegarde échoué : {e}") from e

        base = repo_dir / git_base_path if git_base_path else repo_dir
        if not base.is_dir():
            raise HTTPException(422, f"sous-répertoire '{git_base_path}' introuvable dans le dépôt")
        report = await restore_tree(pool, base, only_workspace=workspace)
        log.info(
            "restore_git_done",
            point=remote_point_slug,
            docs_created=report.docs_created,
            docs_updated=report.docs_updated,
            errors=len(report.errors),
        )
        return report
    finally:
        if ssh_key_path:
            await asyncio.to_thread(delete_key_file, ssh_key_path)
        shutil.rmtree(tmp, ignore_errors=True)

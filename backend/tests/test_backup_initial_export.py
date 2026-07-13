"""Premier run d'un job git_sync : export initial complet du périmètre.

Le journal des changements ne couvre pas les documents antérieurs à sa mise
en place (ou purgés) : avec un curseur à 0, le run doit exporter TOUT le
périmètre, pas seulement ce que le journal mentionne.
"""

from __future__ import annotations

import pathlib
import uuid

import asyncpg
import pytest
from git import Repo

from docflow.backup.git_sync import run_git_sync
from docflow.documents import service as doc_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


def _seed_remote(tmp_path: pathlib.Path) -> pathlib.Path:
    remote_dir = tmp_path / "remote.git"
    Repo.init(remote_dir, bare=True)
    seed = Repo.init(tmp_path / "seed")
    with seed.config_writer() as cw:
        cw.set_value("user", "name", "seed")
        cw.set_value("user", "email", "seed@test.local")
    (pathlib.Path(seed.working_dir) / "README.md").write_text("seed", encoding="utf-8")
    seed.git.add(A=True)
    seed.index.commit("seed")
    seed.create_remote("origin", str(remote_dir))
    seed.remotes.origin.push("HEAD:refs/heads/main")
    return remote_dir


@pytest.mark.usefixtures("test_workspace")
async def test_first_run_exports_documents_absent_from_changelog(
    db_pool: asyncpg.Pool, tmp_path: pathlib.Path
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="task", label="Task"))
    wk: uuid.UUID = await db_pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug=$1", _WS
    )
    ft: uuid.UUID = await db_pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='task'", wk
    )
    block_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key)"
        " VALUES ('blk', 'blk', $1, $2) RETURNING id",
        ft,
        wk,
    )
    await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Ancien", slug="ancien", block_id=block_id, functional_type_slug="task"
        ),
    )
    # Simule un document antérieur au journal : purge des entrées du workspace
    await db_pool.execute("DELETE FROM document_change_log WHERE workspace_technical_key = $1", wk)

    remote_dir = _seed_remote(tmp_path)
    result = await run_git_sync(
        db_pool,
        job_id=uuid.uuid4(),
        workspace_technical_key=wk,
        workspace_slug=_WS,
        last_change_seq=0,
        remote_url=str(remote_dir),
        git_branch="main",
        git_base_path=None,
        ssh_key_path=None,
        repos_root=tmp_path / "repos",
    )
    assert result["files_written"] == 3  # ancien.md + ancien.json + _block.yaml
    assert result["commit_sha"] is not None

    check = Repo.clone_from(str(remote_dir), tmp_path / "check", branch="main")
    tree = pathlib.Path(check.working_dir)
    # Arborescence : workspace / bloc / document
    assert (tree / _WS / "blk" / "ancien.md").exists()
    assert (tree / _WS / "blk" / "ancien.json").exists()
    # Métadonnées du bloc : slug + template du type racine
    meta = (tree / _WS / "blk" / "_block.yaml").read_text(encoding="utf-8")
    assert "block: blk" in meta
    assert "type: task" in meta
    assert "slug: task" in meta


@pytest.mark.usefixtures("test_workspace")
async def test_incremental_run_uses_block_paths(
    db_pool: asyncpg.Pool, tmp_path: pathlib.Path
) -> None:
    """Après le run initial, un nouveau document part sous workspace/bloc/…"""
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="task", label="Task"))
    wk: uuid.UUID = await db_pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug=$1", _WS
    )
    ft: uuid.UUID = await db_pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='task'", wk
    )
    block_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key)"
        " VALUES ('blk', 'blk', $1, $2) RETURNING id",
        ft,
        wk,
    )
    remote_dir = _seed_remote(tmp_path)

    common = dict(
        job_id=uuid.uuid4(),
        workspace_technical_key=wk,
        workspace_slug=_WS,
        remote_url=str(remote_dir),
        git_branch="main",
        git_base_path=None,
        ssh_key_path=None,
        repos_root=tmp_path / "repos",
    )
    first = await run_git_sync(db_pool, last_change_seq=0, **common)

    await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(title="Après", slug="apres", block_id=block_id, functional_type_slug="task"),
    )
    second = await run_git_sync(db_pool, last_change_seq=first["last_change_seq"], **common)
    assert second["commit_sha"] is not None

    check = Repo.clone_from(str(remote_dir), tmp_path / "check", branch="main")
    tree = pathlib.Path(check.working_dir)
    assert (tree / _WS / "blk" / "apres.md").exists()
    assert (tree / _WS / "blk" / "_block.yaml").exists()

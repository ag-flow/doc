"""Aller-retour du miroir git : export git_sync → restore_tree.

Le miroir exporté (workspace / blocs / _block.yaml / documents) doit suffire à
recréer le contenu documentaire sur une instance où le workspace a disparu,
et être idempotent en restauration par-dessus l'existant.
"""

from __future__ import annotations

import pathlib
import uuid

import asyncpg
from git import Repo

from docflow.backup.git_sync import run_git_sync
from docflow.backup.restore_git import restore_tree
from docflow.documents import service as doc_svc
from docflow.schemas.document import DocumentCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.schemas.workspace import WorkspaceCreate
from docflow.types import service as type_svc
from docflow.workspaces import service as ws_svc

_WS = "restore-ws"


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


async def _build_fixture(db_pool: asyncpg.Pool) -> None:
    """Workspace avec type hiérarchique, bloc, et deux documents parent/enfant."""
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug=_WS, label="Restore"), None)
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    await type_svc.create_type(
        db_pool, _WS, FunctionalTypeCreate(slug="story", label="Story", parent_slug="epic")
    )
    wk: uuid.UUID = await db_pool.fetchval(
        "SELECT workspace_technical_key FROM workspace WHERE slug=$1", _WS
    )
    ft: uuid.UUID = await db_pool.fetchval(
        "SELECT id FROM functional_type WHERE workspace_technical_key=$1 AND slug='epic'", wk
    )
    block_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key)"
        " VALUES ('planner', 'Planner', $1, $2) RETURNING id",
        ft,
        wk,
    )
    parent = await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Épopée 1",
            slug="epopee-1",
            block_id=block_id,
            functional_type_slug="epic",
            content="# Épopée",
        ),
    )
    await doc_svc.create_document(
        db_pool,
        _WS,
        DocumentCreate(
            title="Story 1",
            slug="story-1",
            block_id=block_id,
            parent_id=parent.doc_technical_key,
            functional_type_slug="story",
            content="détail de la story",
        ),
    )


async def test_git_mirror_round_trip(db_pool: asyncpg.Pool, tmp_path: pathlib.Path) -> None:
    await _build_fixture(db_pool)
    try:
        wk: uuid.UUID = await db_pool.fetchval(
            "SELECT workspace_technical_key FROM workspace WHERE slug=$1", _WS
        )
        remote_dir = _seed_remote(tmp_path)
        await run_git_sync(
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

        # Sinistre : le workspace disparaît entièrement (cascade blocs/docs/types)
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", _WS)

        clone = Repo.clone_from(str(remote_dir), tmp_path / "clone", branch="main")
        report = await restore_tree(db_pool, pathlib.Path(clone.working_dir))
        assert report.errors == []
        assert report.workspaces_created == 1
        assert report.blocks_created == 1
        assert report.docs_created == 2

        # Structure recréée : types (hiérarchie), bloc, documents avec contenu
        wk2: uuid.UUID = await db_pool.fetchval(
            "SELECT workspace_technical_key FROM workspace WHERE slug=$1", _WS
        )
        types = {
            r["slug"]: r["parent"]
            for r in await db_pool.fetch(
                "SELECT slug, parent FROM functional_type WHERE workspace_technical_key=$1", wk2
            )
        }
        assert set(types) == {"epic", "story"}
        row = await db_pool.fetchrow(
            """
            SELECT d.title, dv.content, p.slug AS parent_slug
            FROM document d
            JOIN document_version dv ON dv.document_ref = d.doc_technical_key
                 AND dv.version_number = d.version
            LEFT JOIN document p ON p.doc_technical_key = d.parent
            WHERE d.workspace_technical_key = $1 AND d.slug = 'story-1'
            """,
            wk2,
        )
        assert row is not None
        assert row["title"] == "Story 1"
        assert row["content"] == "détail de la story"
        assert row["parent_slug"] == "epopee-1"

        # Idempotence : re-restaurer par-dessus ne crée ni ne modifie rien
        report2 = await restore_tree(db_pool, pathlib.Path(clone.working_dir))
        assert report2.errors == []
        assert report2.workspaces_created == 0
        assert report2.blocks_created == 0
        assert report2.docs_created == 0
        assert report2.docs_updated == 0
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", _WS)


async def test_restore_from_remote_round_trip(
    db_pool: asyncpg.Pool, tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Réalimentation via l'API : clone du remote (auth simulée) + restore_tree."""
    from docflow.backup import restore_remote

    await _build_fixture(db_pool)
    try:
        wk: uuid.UUID = await db_pool.fetchval(
            "SELECT workspace_technical_key FROM workspace WHERE slug=$1", _WS
        )
        remote_dir = _seed_remote(tmp_path)
        await run_git_sync(
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
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", _WS)

        async def fake_auth(pool, slug, settings):  # type: ignore[no-untyped-def]
            return str(remote_dir), None, {}

        class _FakePoint:
            point_type = "git"
            git_branch = "main"

        async def fake_get_point(pool, slug):  # type: ignore[no-untyped-def]
            return _FakePoint()

        monkeypatch.setattr(restore_remote, "resolve_git_auth", fake_auth)
        monkeypatch.setattr(restore_remote.rp_svc, "get_point", fake_get_point)

        report = await restore_remote.restore_from_remote(
            db_pool, object(), remote_point_slug="whatever"
        )
        assert report.errors == []
        assert report.workspaces_created == 1
        assert report.docs_created == 2
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", _WS)

"""Tests de la réconciliation git_sync (DB-01/DB-02) — sans base de données.

Couvre :
- `expected_file_paths` : calcul des chemins attendus par chemin complet
  (les slugs ne sont uniques que par fratrie, cf. 0030_document_slug.sql) ;
- `find_orphan_files` : détection des orphelins par chemin, pas par slug ;
- `_git_phase` : bout-en-bout sur un remote git local — un workspace absent
  du périmètre de réconciliation n'est JAMAIS touché, un document déplacé ne
  laisse pas de doublon à l'ancien chemin.
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, datetime
from typing import Any

from git import Repo

from docflow.backup.git_files import expected_file_paths, find_orphan_files
from docflow.backup.git_sync import _git_phase


def _doc(slug: str | None, parent: uuid.UUID | None = None) -> dict[str, Any]:
    return {"id": uuid.uuid4(), "slug": slug, "parent": parent}


# ── _expected_file_paths ──────────────────────────────────────────────────────


def test_expected_paths_nested_tree() -> None:
    root = _doc("epic-1")
    child = _doc("feat-1", parent=root["id"])
    paths = expected_file_paths("ws-a", [root, child])
    assert paths == {
        "ws-a/epic-1.md",
        "ws-a/epic-1.json",
        "ws-a/epic-1/feat-1.md",
        "ws-a/epic-1/feat-1.json",
    }


def test_expected_paths_same_slug_different_parents() -> None:
    """Les slugs ne sont uniques que par fratrie : deux docs 'notes' sous des
    parents différents produisent deux chemins distincts, tous deux attendus."""
    a = _doc("epic-a")
    b = _doc("epic-b")
    notes_a = _doc("notes", parent=a["id"])
    notes_b = _doc("notes", parent=b["id"])
    paths = expected_file_paths("ws", [a, b, notes_a, notes_b])
    assert "ws/epic-a/notes.md" in paths
    assert "ws/epic-b/notes.md" in paths


def test_expected_paths_skips_invalid_or_missing_slug() -> None:
    ok = _doc("valid")
    no_slug = _doc(None)
    bad_slug = _doc("Not A Slug!")
    child_of_no_slug = _doc("child", parent=no_slug["id"])
    paths = expected_file_paths("ws", [ok, no_slug, bad_slug, child_of_no_slug])
    # Seul le doc valide a un chemin ; un ancêtre sans slug invalide toute la branche
    assert paths == {"ws/valid.md", "ws/valid.json"}


def test_expected_paths_skips_dangling_parent() -> None:
    orphan = _doc("orphan", parent=uuid.uuid4())  # parent absent du workspace
    assert expected_file_paths("ws", [orphan]) == set()


# ── _find_orphan_files ────────────────────────────────────────────────────────


def _touch(base: pathlib.Path, rel: str) -> pathlib.Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    return p


def test_find_orphans_by_full_path_not_slug(tmp_path: pathlib.Path) -> None:
    """Un doc déplacé laisse un fichier à l'ancien chemin : même slug, mais le
    chemin complet n'est plus attendu → orphelin (le matching par p.stem le
    ratait)."""
    _touch(tmp_path, "ws/epic-1/feat-1.md")
    _touch(tmp_path, "ws/epic-1/feat-1.json")
    _touch(tmp_path, "ws/feat-1.md")
    _touch(tmp_path, "ws/feat-1.json")
    expected = {"ws/feat-1.md", "ws/feat-1.json"}
    orphans = {
        p.relative_to(tmp_path).as_posix() for p in find_orphan_files(tmp_path, "ws", expected)
    }
    assert orphans == {"ws/epic-1/feat-1.md", "ws/epic-1/feat-1.json"}


def test_find_orphans_only_in_given_workspace(tmp_path: pathlib.Path) -> None:
    _touch(tmp_path, "ws-a/stale.md")
    _touch(tmp_path, "ws-b/doc-b.md")
    orphans = find_orphan_files(tmp_path, "ws-a", expected_paths=set())
    assert [p.relative_to(tmp_path).as_posix() for p in orphans] == ["ws-a/stale.md"]


def test_find_orphans_missing_workspace_dir(tmp_path: pathlib.Path) -> None:
    assert find_orphan_files(tmp_path, "absent", {"absent/x.md"}) == []


# ── _git_phase bout-en-bout (remote git local, aucun réseau ni DB) ───────────


def _seed_remote(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """Crée un dépôt bare avec une branche main contenant `files`."""
    remote_dir = tmp_path / "remote.git"
    Repo.init(remote_dir, bare=True)
    seed = Repo.init(tmp_path / "seed")
    with seed.config_writer() as cw:
        cw.set_value("user", "name", "seed")
        cw.set_value("user", "email", "seed@test.local")
    for rel, content in files.items():
        _touch(pathlib.Path(seed.working_dir), rel).write_text(content, encoding="utf-8")
    seed.git.add(A=True)
    seed.index.commit("seed")
    seed.create_remote("origin", str(remote_dir))
    seed.remotes.origin.push("HEAD:refs/heads/main")
    return remote_dir


def test_git_phase_reconciles_covered_ws_only(tmp_path: pathlib.Path) -> None:
    """Job instance-wide : seul ws-a a des changements. ws-b (non couvert) ne
    doit JAMAIS être touché ; le doc déplacé de ws-a ne laisse pas de doublon."""
    remote_dir = _seed_remote(
        tmp_path,
        {
            "ws-a/epic-1.md": "epic",
            "ws-a/epic-1.json": "{}",
            "ws-a/epic-1/feat-1.md": "old",
            "ws-a/epic-1/feat-1.json": "{}",
            "ws-b/doc-b.md": "b",
            "ws-b/doc-b.json": "{}",
        },
    )
    doc = {
        "title": "Feat 1",
        "content": "moved",
        "functional_type_slug": None,
        "updated_at": datetime.now(tz=UTC),
        "properties": {},
    }
    # feat-1 déplacé à la racine de ws-a ; epic-1 inchangé mais toujours attendu
    reconcile = {
        "ws-a": {
            "ws-a/epic-1.md",
            "ws-a/epic-1.json",
            "ws-a/feat-1.md",
            "ws-a/feat-1.json",
        }
    }
    written, deleted, sha = _git_phase(
        repo_dir=tmp_path / "job",
        remote_url=str(remote_dir),
        git_branch="main",
        git_base_path=None,
        ssh_key_path=None,
        git_http_env={},
        to_write=[(["ws-a", "feat-1"], doc)],
        reconcile=reconcile,
    )
    assert written == 2  # feat-1.md + feat-1.json
    assert deleted == 2  # ancien chemin ws-a/epic-1/feat-1.{md,json}
    assert sha is not None

    check = Repo.clone_from(str(remote_dir), tmp_path / "check", branch="main")
    tree = pathlib.Path(check.working_dir)
    assert (tree / "ws-a/feat-1.md").read_text(encoding="utf-8") == "moved"
    assert not (tree / "ws-a/epic-1/feat-1.md").exists()
    assert (tree / "ws-a/epic-1.md").exists()  # doc inchangé conservé
    # Workspace non couvert par le batch : intact
    assert (tree / "ws-b/doc-b.md").exists()
    assert (tree / "ws-b/doc-b.json").exists()


def test_git_phase_prunes_deleted_workspace_dirs(tmp_path: pathlib.Path) -> None:
    """Un répertoire de workspace MARQUÉ dont le workspace n'existe plus est
    purgé ; un répertoire étranger (sans marqueur) n'est JAMAIS touché."""
    remote_dir = _seed_remote(
        tmp_path,
        {
            "ws-dead/.docflow-workspace": "ws-dead",
            "ws-dead/doc.md": "x",
            "ws-dead/doc.json": "{}",
            "ws-live/.docflow-workspace": "ws-live",
            "ws-live/doc.md": "y",
            "ws-live/doc.json": "{}",
            "docs/notes.md": "contenu étranger au sync",
        },
    )
    written, deleted, sha = _git_phase(
        repo_dir=tmp_path / "job",
        remote_url=str(remote_dir),
        git_branch="main",
        git_base_path=None,
        ssh_key_path=None,
        git_http_env={},
        to_write=[],
        reconcile={},
        live_workspace_slugs={"ws-live"},
    )
    assert deleted == 2  # ws-dead/doc.{md,json}
    assert sha is not None

    check = Repo.clone_from(str(remote_dir), tmp_path / "check", branch="main")
    tree = pathlib.Path(check.working_dir)
    assert not (tree / "ws-dead").exists()
    assert (tree / "ws-live/doc.md").exists()
    assert (tree / "docs/notes.md").exists()  # pas de marqueur → intouchable


def test_git_phase_writes_workspace_marker(tmp_path: pathlib.Path) -> None:
    remote_dir = _seed_remote(tmp_path, {"README.md": "seed"})
    doc = {
        "title": "Doc",
        "content": "c",
        "functional_type_slug": None,
        "updated_at": datetime.now(tz=UTC),
        "properties": {},
    }
    _git_phase(
        repo_dir=tmp_path / "job",
        remote_url=str(remote_dir),
        git_branch="main",
        git_base_path=None,
        ssh_key_path=None,
        git_http_env={},
        to_write=[(["ws-a", "doc"], doc)],
        reconcile={"ws-a": {"ws-a/doc.md", "ws-a/doc.json"}},
    )
    check = Repo.clone_from(str(remote_dir), tmp_path / "check", branch="main")
    marker = pathlib.Path(check.working_dir) / "ws-a" / ".docflow-workspace"
    assert marker.read_text(encoding="utf-8") == "ws-a"

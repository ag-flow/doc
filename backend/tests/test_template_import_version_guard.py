"""Import de template : décision de version et écriture sous la MÊME transaction.

La lecture de version, le contrôle de régression et le calcul du diff se font
désormais dans la transaction d'écriture, et l'upsert de
`workspace_template_import` porte une garde SQL : un import plus ancien ne peut
jamais rétrograder la version enregistrée, même si le contrôle applicatif a lu
un état périmé (course entre deux imports).
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest
import yaml
from fastapi import HTTPException

import docflow.templates.router as tr
from docflow.schemas.workspace import WorkspaceCreate
from docflow.templates.importer import (
    ConcurrentImportError,
    VersionConflictError,
    _record_import,
    run_import,
)
from docflow.templates.models import PropDef, Template, TypeDef
from docflow.workspaces import service as ws_svc

_TEMPLATE_SLUG = "guard-test"


class _FakeRequest:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(pool=pool))
        self.state = SimpleNamespace()


def _tpl(version: int, *, extra_type: str | None = None) -> Template:
    types = [
        TypeDef(
            slug="epic",
            label="Epic",
            properties=[PropDef(slug="titre", label="Titre", type="text")],
        )
    ]
    if extra_type is not None:
        types.append(TypeDef(slug=extra_type, label=extra_type.capitalize()))
    return Template(
        version=version,
        template=_TEMPLATE_SLUG,
        label="Guard Test",
        functional_types=types,
    )


async def _db_version(pool: asyncpg.Pool, ws_slug: str) -> int | None:
    return await pool.fetchval(  # type: ignore[no-any-return]
        "SELECT wi.version FROM workspace_template_import wi"
        " JOIN workspace w ON w.workspace_technical_key = wi.workspace_technical_key"
        " WHERE w.slug = $1 AND wi.template = $2",
        ws_slug,
        _TEMPLATE_SLUG,
    )


async def _type_slugs(pool: asyncpg.Pool, ws_slug: str) -> set[str]:
    rows = await pool.fetch(
        "SELECT ft.slug FROM functional_type ft"
        " JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key"
        " WHERE w.slug = $1",
        ws_slug,
    )
    return {r["slug"] for r in rows}


@pytest.fixture()
async def ws(db_pool: asyncpg.Pool, request: pytest.FixtureRequest) -> Any:
    slug = f"gt-{abs(hash(request.node.name)) % 10**8}"
    await ws_svc.create_workspace(db_pool, WorkspaceCreate(slug=slug, label="Guard"), None)
    yield slug
    await db_pool.execute("DELETE FROM workspace WHERE slug = $1", slug)


# ── Contrôle de régression (désormais sous transaction) ─────────────────────


async def test_import_older_version_rejected(db_pool: asyncpg.Pool, ws: str) -> None:
    await run_import(db_pool, ws, _tpl(5))

    with pytest.raises(VersionConflictError):
        await run_import(db_pool, ws, _tpl(3, extra_type="feature"))

    assert await _db_version(db_pool, ws) == 5
    assert "feature" not in await _type_slugs(db_pool, ws)


# ── Garde SQL de l'upsert (invariant, pas la course elle-même) ──────────────


async def test_record_import_guard_refuses_downgrade(db_pool: asyncpg.Pool, ws: str) -> None:
    await run_import(db_pool, ws, _tpl(5))
    wk = await db_pool.fetchval("SELECT workspace_technical_key FROM workspace WHERE slug = $1", ws)

    async with db_pool.acquire() as conn:
        assert await _record_import(conn, str(wk), _TEMPLATE_SLUG, 3) is False
        assert await _db_version(db_pool, ws) == 5

        assert await _record_import(conn, str(wk), _TEMPLATE_SLUG, 5) is True
        assert await _record_import(conn, str(wk), _TEMPLATE_SLUG, 7) is True
        assert await _db_version(db_pool, ws) == 7


# ── Collision concurrente → erreur métier, jamais un 500 ────────────────────


async def test_unique_violation_becomes_concurrent_import_error(
    db_pool: asyncpg.Pool, ws: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un import concurrent qui insère les mêmes structures fait remonter une
    UniqueViolationError d'asyncpg : elle doit devenir une erreur du module."""
    import docflow.templates.importer as imp

    async def _boom(*_a: object, **_kw: object) -> None:
        raise asyncpg.UniqueViolationError("duplicate key value violates unique constraint")

    monkeypatch.setattr(imp, "_write_types", _boom)

    with pytest.raises(ConcurrentImportError):
        await run_import(db_pool, ws, _tpl(1))

    assert await _type_slugs(db_pool, ws) == set()
    assert await _db_version(db_pool, ws) is None


async def test_route_concurrent_import_returns_409(
    db_pool: asyncpg.Pool,
    ws: str,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tr, "_TEMPLATES_DIR", tmp_path)
    (tmp_path / f"{_TEMPLATE_SLUG}.yaml").write_text(
        yaml.dump(_tpl(1).model_dump(), allow_unicode=True)
    )

    async def _boom(*_a: object, **_kw: object) -> None:
        raise ConcurrentImportError("import concurrent")

    monkeypatch.setattr(tr, "run_import", _boom)

    body = tr.ImportTemplateIn(template=_TEMPLATE_SLUG)
    with pytest.raises(HTTPException) as exc:
        await tr.import_template(ws, body, _FakeRequest(db_pool))  # type: ignore[arg-type]
    assert exc.value.status_code == 409


# ── Non-régression des trois chemins de sortie ──────────────────────────────


async def test_import_nominal_applies(db_pool: asyncpg.Pool, ws: str) -> None:
    report = await run_import(db_pool, ws, _tpl(1))
    assert report.applied
    assert not report.no_op
    assert not report.dry_run
    assert await _type_slugs(db_pool, ws) == {"epic"}
    assert await _db_version(db_pool, ws) == 1


async def test_import_same_version_is_no_op(db_pool: asyncpg.Pool, ws: str) -> None:
    await run_import(db_pool, ws, _tpl(1))
    before = await db_pool.fetchval(
        "SELECT wi.imported_at FROM workspace_template_import wi"
        " JOIN workspace w ON w.workspace_technical_key = wi.workspace_technical_key"
        " WHERE w.slug = $1 AND wi.template = $2",
        ws,
        _TEMPLATE_SLUG,
    )

    report = await run_import(db_pool, ws, _tpl(1))
    assert report.no_op
    assert not report.applied

    after = await db_pool.fetchval(
        "SELECT wi.imported_at FROM workspace_template_import wi"
        " JOIN workspace w ON w.workspace_technical_key = wi.workspace_technical_key"
        " WHERE w.slug = $1 AND wi.template = $2",
        ws,
        _TEMPLATE_SLUG,
    )
    assert before == after


async def test_import_no_op_stamps_provenance(db_pool: asyncpg.Pool, ws: str) -> None:
    """Le chemin no_op estampille toujours la provenance des types sans source."""
    await run_import(db_pool, ws, _tpl(1))
    await db_pool.execute(
        "UPDATE functional_type SET source_template = NULL"
        " WHERE slug = 'epic' AND workspace_technical_key ="
        " (SELECT workspace_technical_key FROM workspace WHERE slug = $1)",
        ws,
    )

    report = await run_import(db_pool, ws, _tpl(1))
    assert report.no_op

    source = await db_pool.fetchval(
        "SELECT ft.source_template FROM functional_type ft"
        " JOIN workspace w ON w.workspace_technical_key = ft.workspace_technical_key"
        " WHERE w.slug = $1 AND ft.slug = 'epic'",
        ws,
    )
    assert source == _TEMPLATE_SLUG


async def test_import_dry_run_writes_nothing(db_pool: asyncpg.Pool, ws: str) -> None:
    report = await run_import(db_pool, ws, _tpl(1), dry_run=True)
    assert report.dry_run
    assert not report.applied
    assert await _type_slugs(db_pool, ws) == set()
    assert await _db_version(db_pool, ws) is None

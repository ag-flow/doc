"""Parité REST / MCP — template_slug à la création de bloc.

L'auto-import vit désormais dans blocks/service.create_block (même code pour les
deux surfaces), dans la MÊME transaction que la création du bloc.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.blocks import service as block_svc
from docflow.schemas.block import DataBlockCreate
from docflow.templates import catalog
from docflow.templates.models import Template

_WS = "test-ws"  # fourni par la fixture test_workspace


def _tpl(slug: str, type_slugs: list[str]) -> Template:
    return Template.model_validate(
        {
            "version": 1,
            "template": slug,
            "label": slug.upper(),
            "functional_types": [{"slug": s, "label": s.title()} for s in type_slugs],
        }
    )


@pytest.fixture()
def stub_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """catalog.find_template sans filesystem : 't-min' (type note), 't-two'
    (note + extra), tout autre slug → introuvable (ValueError → 404)."""
    known = {"t-min": _tpl("t-min", ["note"]), "t-two": _tpl("t-two", ["note", "extra"])}

    def _fake(slug: str) -> Template:
        if slug in known:
            return known[slug]
        raise ValueError(f"template '{slug}' introuvable")

    monkeypatch.setattr(catalog, "find_template", _fake)


async def _type_exists(pool: asyncpg.Pool, slug: str) -> bool:
    return bool(
        await pool.fetchval(
            "SELECT 1 FROM functional_type ft JOIN workspace w "
            "ON w.workspace_technical_key = ft.workspace_technical_key "
            "WHERE w.slug = $1 AND ft.slug = $2",
            _WS,
            slug,
        )
    )


async def _block_exists(pool: asyncpg.Pool, slug: str) -> bool:
    return bool(
        await pool.fetchval(
            "SELECT 1 FROM data_block b JOIN workspace w "
            "ON w.workspace_technical_key = b.workspace_technical_key "
            "WHERE w.slug = $1 AND b.slug = $2",
            _WS,
            slug,
        )
    )


async def test_template_slug_importe_le_type_puis_cree_le_bloc(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], stub_catalog: None
) -> None:
    assert not await _type_exists(db_pool, "note")
    out = await block_svc.create_block(
        db_pool,
        _WS,
        DataBlockCreate(slug="b1", label="B1", functional_type_slug="note", template_slug="t-min"),
    )
    assert out.slug == "b1"
    assert await _type_exists(db_pool, "note")
    assert await _block_exists(db_pool, "b1")


async def test_reimport_idempotent_pas_de_doublon(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], stub_catalog: None
) -> None:
    await block_svc.create_block(
        db_pool,
        _WS,
        DataBlockCreate(slug="b1", label="B1", functional_type_slug="note", template_slug="t-min"),
    )
    # Deuxième bloc réutilisant le même template : import no-op, aucun doublon.
    await block_svc.create_block(
        db_pool,
        _WS,
        DataBlockCreate(slug="b2", label="B2", functional_type_slug="note", template_slug="t-min"),
    )
    count = await db_pool.fetchval(
        "SELECT count(*) FROM functional_type ft JOIN workspace w "
        "ON w.workspace_technical_key = ft.workspace_technical_key "
        "WHERE w.slug = $1 AND ft.slug = 'note'",
        _WS,
    )
    assert count == 1
    assert await _block_exists(db_pool, "b2")


async def test_template_inconnu_404_aucun_bloc(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], stub_catalog: None
) -> None:
    with pytest.raises(HTTPException) as exc:
        await block_svc.create_block(
            db_pool,
            _WS,
            DataBlockCreate(
                slug="b3", label="B3", functional_type_slug="note", template_slug="inconnu"
            ),
        )
    assert exc.value.status_code == 404
    assert not await _block_exists(db_pool, "b3")


async def test_type_absent_du_template_422_et_import_annule(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], stub_catalog: None
) -> None:
    """functional_type_slug hors template → 422, ET l'import est ANNULÉ (atomicité :
    l'échec de résolution du type rollback la transaction, donc le type importé aussi)."""
    with pytest.raises(HTTPException) as exc:
        await block_svc.create_block(
            db_pool,
            _WS,
            DataBlockCreate(
                slug="b4", label="B4", functional_type_slug="ghost", template_slug="t-min"
            ),
        )
    assert exc.value.status_code == 422
    assert not await _block_exists(db_pool, "b4")
    assert not await _type_exists(db_pool, "note")  # import rollback (rien de partiel)


async def test_atomicite_slug_deja_pris_rollback_import(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], stub_catalog: None
) -> None:
    """Si la création du bloc échoue (slug déjà pris), l'import est annulé : le
    NOUVEAU type du template n'est pas laissé en base."""
    await block_svc.create_block(
        db_pool,
        _WS,
        DataBlockCreate(
            slug="dup", label="Dup", functional_type_slug="note", template_slug="t-min"
        ),
    )
    # Rejeu du même slug avec un template qui AJOUTERAIT 'extra' → 409, extra non importé.
    with pytest.raises(HTTPException) as exc:
        await block_svc.create_block(
            db_pool,
            _WS,
            DataBlockCreate(
                slug="dup", label="Dup", functional_type_slug="note", template_slug="t-two"
            ),
        )
    assert exc.value.status_code == 409
    assert not await _type_exists(db_pool, "extra")  # import annulé


async def test_mcp_create_block_avec_template_parite(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object], stub_catalog: None
) -> None:
    """La surface MCP emprunte le même code : create_block(template_slug) importe."""
    import json

    from docflow.mcp.server import _create_block, configure

    configure(db_pool)
    res = _create_block(
        db_pool,
        {
            "workspace_slug": _WS,
            "slug": "m1",
            "label": "M1",
            "functional_type_slug": "note",
            "template_slug": "t-min",
        },
    )
    payload = json.loads((await res)[0].text)
    assert payload.get("created") is True
    assert await _type_exists(db_pool, "note")
    assert await _block_exists(db_pool, "m1")


def test_mcp_authz_create_block_template_exige_admin() -> None:
    """Garde MCP : une clé scopée NON-admin ne peut pas importer via create_block."""
    from docflow.apikeys.schemas import ApiProfileScopeOut
    from docflow.mcp import server
    from docflow.mcp.session import McpSession, reset_current_session, set_current_session

    scope = ApiProfileScopeOut(
        id=uuid.uuid4(), workspace_slug=_WS, block_slug=None, read_only=False
    )
    session = McpSession(user=None, api_key_scopes=[scope], api_key_admin=False)  # type: ignore[arg-type]
    token = set_current_session(session)
    try:
        # Avec template_slug → refus admin.
        denied = server._check_tool_authz(
            "create_block", {"workspace_slug": _WS, "template_slug": "t-min"}
        )
        assert denied is not None
        # Sans template_slug → pas de refus admin (le scope write du ws suffit).
        allowed = server._check_tool_authz("create_block", {"workspace_slug": _WS})
        assert allowed is None
    finally:
        reset_current_session(token)

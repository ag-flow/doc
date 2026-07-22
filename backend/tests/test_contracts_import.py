"""Import d'un contrat OpenAPI : URL source → téléchargement immédiat du spec.

Régression : un import par URL stockait un spec vide (raw_spec={}) jusqu'à un
refresh, donc aucune opération/méthode n'apparaissait dans les automates.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import pytest

from docflow.contracts import service
from docflow.schemas.contracts import ContractImport

_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"version": "1.2.3"},
    "paths": {
        "/index": {"post": {"operationId": "index", "summary": "Index a document"}},
    },
}


class _Resp:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return _SPEC


class _Client:
    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *a: Any) -> bool:
        return False

    async def get(self, url: str) -> _Resp:
        return _Resp()


async def _noop(url: str) -> None:
    return None


async def test_import_by_url_fetches_spec_and_exposes_operations(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "validate_public_url", _noop)
    monkeypatch.setattr(service.httpx, "AsyncClient", _Client)

    out = await service.import_contract(
        db_pool,
        ContractImport(label="rag", source_url="https://rag.example/openapi", raw_spec={}),
    )
    assert out.version == "1.2.3"  # info.version extrait du spec téléchargé

    detail = await service.get_contract_detail(db_pool, out.id)
    assert len(detail.operations) == 1
    op = detail.operations[0]
    assert op.method == "POST"
    assert op.path == "/index"
    assert op.operation_id == "index"


async def test_import_inline_spec_does_not_fetch(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Si un spec inline est fourni, aucun fetch (le client factice lèverait sinon).
    def _boom(*a: Any, **k: Any) -> None:
        raise AssertionError("ne doit pas fetch quand raw_spec est fourni")

    monkeypatch.setattr(service.httpx, "AsyncClient", _boom)
    out = await service.import_contract(
        db_pool,
        ContractImport(label="inline", raw_spec=_SPEC),
    )
    detail = await service.get_contract_detail(db_pool, out.id)
    assert len(detail.operations) == 1

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


class _RedirectCapturingClient(_Client):
    """Comme `_Client`, mais garde les kwargs de construction du client.

    Sert à vérifier que `_fetch_spec` ne suit pas de redirection (SSRF) :
    une redirection non revalidée pourrait viser un hôte interne.
    """

    captured_kwargs: dict[str, Any] = {}

    def __init__(self, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        _RedirectCapturingClient.captured_kwargs = k


async def test_fetch_spec_does_not_follow_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "validate_public_url", _noop)
    monkeypatch.setattr(service.httpx, "AsyncClient", _RedirectCapturingClient)

    await service._fetch_spec("https://rag.example/openapi")

    assert _RedirectCapturingClient.captured_kwargs.get("follow_redirects") is False


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


_SECURED_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"version": "1"},
    "components": {
        "securitySchemes": {
            "BearerApiKey": {"type": "http", "scheme": "bearer"},
            "XKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        }
    },
    "paths": {
        "/bearer": {"post": {"operationId": "b", "security": [{"BearerApiKey": []}]}},
        "/apikey": {"get": {"operationId": "a", "security": [{"XKey": []}]}},
        "/open": {"get": {"operationId": "o"}},
    },
}


def test_server_urls_extracted() -> None:
    assert service._server_urls({"servers": [{"url": "http://rag.example"}]}) == [
        "http://rag.example"
    ]
    assert service._server_urls({"servers": [{"url": "  "}, {"nope": 1}, "x"]}) == []
    assert service._server_urls({}) == []


async def test_get_contract_spec_returns_raw(db_pool: asyncpg.Pool) -> None:
    out = await service.import_contract(db_pool, ContractImport(label="raw", raw_spec=_SPEC))
    spec = await service.get_contract_spec(db_pool, out.id)
    assert spec["openapi"] == "3.1.0"
    assert "/index" in spec["paths"]


async def test_contract_detail_exposes_servers(db_pool: asyncpg.Pool) -> None:
    spec = {**_SPEC, "servers": [{"url": "http://rag.example"}]}
    out = await service.import_contract(db_pool, ContractImport(label="srv", raw_spec=spec))
    detail = await service.get_contract_detail(db_pool, out.id)
    assert detail.servers == ["http://rag.example"]


def test_operation_auth_headers_from_security() -> None:
    ops = {o.operation_id: o for o in service.list_operations(_SECURED_SPEC)}

    bearer = ops["b"].auth_headers
    assert len(bearer) == 1
    assert bearer[0].header == "Authorization"
    assert bearer[0].value_prefix == "Bearer "

    apikey = ops["a"].auth_headers
    assert len(apikey) == 1
    assert apikey[0].header == "X-API-Key"
    assert apikey[0].value_prefix == ""

    # Opération sans security (et pas de security racine) → aucun header d'auth.
    assert ops["o"].auth_headers == []


async def test_refresh_signals_orphaned_operations_used_by_automations(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch, test_workspace: dict
) -> None:
    """DoD écran Contrats : une opération disparue du contrat rafraîchi mais
    encore référencée par un automate est signalée (avec les automates)."""
    monkeypatch.setattr(service, "validate_public_url", _noop)
    monkeypatch.setattr(service.httpx, "AsyncClient", _Client)

    two_ops = {
        **_SPEC,
        "paths": {
            "/index": {"post": {"operationId": "index"}},
            "/purge": {"post": {"operationId": "purge"}},
        },
    }
    out = await service.import_contract(
        db_pool, ContractImport(label="rag", source_url="http://spec.example", raw_spec=two_ops)
    )
    # Corriger le spec stocké : l'import par URL a téléchargé _SPEC (une seule
    # opération) via le mock ; on veut partir de DEUX opérations.
    import json as _json

    await db_pool.execute(
        "UPDATE openapi_contract SET raw_spec=$1::jsonb WHERE id=$2",
        _json.dumps(two_ops),
        out.id,
    )

    wk = test_workspace["workspace_technical_key"]
    auto_id = await db_pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, event_codes, url, "
        "http_method, contract_ref, operation_id) "
        "VALUES ($1, 'Purge auto', ARRAY['docflow.document.updated.v1'], "
        "'http://x', 'POST', $2, 'purge') RETURNING id",
        wk,
        out.id,
    )
    await db_pool.execute(
        "INSERT INTO automation_workspace (automation_ref, workspace_technical_key, position) "
        "VALUES ($1, $2, 1)",
        auto_id,
        wk,
    )

    # Le refresh re-télécharge _SPEC (opération `index` seule) : `purge` disparaît.
    result = await service.refresh_contract(db_pool, out.id)
    assert [o.operation_id for o in result.orphaned_operations] == ["purge"]
    assert result.orphaned_operations[0].automations == ["Purge auto"]

    # Aucun faux positif : les opérations toujours présentes ne remontent pas.
    result2 = await service.refresh_contract(db_pool, out.id)
    assert result2.orphaned_operations == []

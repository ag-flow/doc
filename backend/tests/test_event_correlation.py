"""A2/A3/A4 — le contexte de corrélation dans l'enveloppe et aux frontières.

STANDARD « Traçabilité du contexte ». A1 (le contrat) est couvert par
test_correlation.py ; ici on vérifie le portage en base (A2), l'ingress (A3)
et la propagation/arrêt aux sorties HTTP (A4).
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from docflow.automations import worker as auto_worker
from docflow.documents import service as doc_svc
from docflow.events import outbox
from docflow.observability import correlation as corr
from docflow.observability.middleware import CorrelationMiddleware
from docflow.schemas.document import DocumentCreate
from docflow.schemas.types import FunctionalTypeCreate
from docflow.types import service as type_svc

_WS = "test-ws"


@pytest.fixture()
async def emit(db_pool: asyncpg.Pool):  # type: ignore[no-untyped-def]
    await db_pool.execute("DELETE FROM event_outbox")
    outbox.configure(enabled=True, source="docflow-test")
    yield
    outbox.configure(enabled=False, source="docflow")
    await db_pool.execute("DELETE FROM event_outbox")


# ── A2 : l'enveloppe et les colonnes portent le contexte ──────────────────────


async def test_mutation_sans_amont_naît_kind_document(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block, emit: None
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    block_id = await make_block(_WS, "epic", "epic-block")
    doc = await doc_svc.create_document(
        db_pool, _WS, DocumentCreate(title="A", functional_type_slug="epic", block_id=block_id)
    )
    key = str(doc.doc_technical_key)

    # Journal document_event : kind=document, id = clé technique OPAQUE du doc.
    de = await db_pool.fetchrow(
        "SELECT correlation_id, correlation_kind, origin, traceparent "
        "FROM document_event WHERE document_ref = $1",
        doc.doc_technical_key,
    )
    assert de["correlation_id"] == key
    assert de["correlation_kind"] == "document"
    assert de["origin"] == "doc"
    assert de["traceparent"] is None

    # Outbox producteur : colonnes + enveloppe alignées.
    eo = await db_pool.fetchrow(
        "SELECT correlation_id, correlation_kind, origin, payload FROM event_outbox"
    )
    assert eo["correlation_id"] == key
    assert eo["correlation_kind"] == "document"
    env = json.loads(eo["payload"])
    assert env["_correlationId"] == key
    assert env["_correlationKind"] == "document"
    assert env["_origin"] == "doc"
    # Pas de traceparent entrant → _traceId absent (rien à relayer).
    assert "_traceId" not in env


async def test_contexte_ambiant_est_relayé_sans_réécriture(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block, emit: None
) -> None:
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    block_id = await make_block(_WS, "epic", "epic-block")

    upstream = corr.CorrelationContext(
        origin="workflow",
        correlation_id="wf-thread-777",
        correlation_kind="workflow_instance",
        traceparent="00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    )
    token = corr.bind(upstream)
    try:
        await doc_svc.create_document(
            db_pool, _WS, DocumentCreate(title="B", functional_type_slug="epic", block_id=block_id)
        )
    finally:
        corr.reset(token)

    de = await db_pool.fetchrow(
        "SELECT correlation_id, correlation_kind, origin, traceparent FROM document_event"
    )
    # Relais opaque : le fil amont n'est pas réécrit en kind=document.
    assert de["correlation_id"] == "wf-thread-777"
    assert de["correlation_kind"] == "workflow_instance"
    assert de["origin"] == "workflow"
    assert de["traceparent"] == upstream.traceparent
    env = json.loads((await db_pool.fetchrow("SELECT payload FROM event_outbox"))["payload"])
    assert env["_traceId"] == upstream.traceparent  # relais du traceparent entrant


# ── A3 : ingress fail-closed ──────────────────────────────────────────────────


class _Settings:
    def __init__(self, header: str | None) -> None:
        self.trace_ingress_header = header


def _scope(headers: dict[str, str], ingress_header: str | None) -> dict[str, Any]:
    app = MagicMock()
    app.state = MagicMock()
    app.state.settings = _Settings(ingress_header)
    raw = [(k.encode(), v.encode()) for k, v in headers.items()]
    return {"type": "http", "app": app, "headers": raw}


async def _run_middleware(scope: dict[str, Any]) -> corr.CorrelationContext | None:
    seen: dict[str, corr.CorrelationContext | None] = {}

    async def inner(s: Any, r: Any, snd: Any) -> None:
        seen["ctx"] = corr.current()

    mw = CorrelationMiddleware(inner)
    await mw(scope, AsyncMock(), AsyncMock())
    assert corr.current() is None  # nettoyé après la requête
    return seen["ctx"]


async def test_ingress_appelant_interne_vouché_relaie_le_contexte() -> None:
    incoming = corr.new_context("a2a_task", origin="a2a", correlation_id="ext-1")
    headers = corr.to_baggage_headers(incoming)
    headers["x-internal"] = "1"
    ctx = await _run_middleware(_scope(headers, ingress_header="x-internal"))
    assert ctx is not None and ctx.correlation_id == "ext-1" and ctx.origin == "a2a"


async def test_ingress_sans_marqueur_de_confiance_ignore_le_contexte() -> None:
    incoming = corr.new_context("a2a_task", origin="a2a", correlation_id="ext-1")
    headers = corr.to_baggage_headers(incoming)  # baggage présent, mais pas de marqueur
    ctx = await _run_middleware(_scope(headers, ingress_header="x-internal"))
    assert ctx is None  # fail-closed


async def test_ingress_desactive_par_defaut() -> None:
    headers = corr.to_baggage_headers(corr.new_context("a2a_task"))
    headers["x-internal"] = "1"
    ctx = await _run_middleware(_scope(headers, ingress_header=None))
    assert ctx is None  # aucun en-tête de confiance configuré → jamais de relais


# ── A4 : propagation interne / arrêt externe ──────────────────────────────────


def test_is_internal_target_allowlist() -> None:
    s = _cfg(["idx.yoops.internal", "ragflow.svc"])
    assert auto_worker._is_internal_target("https://ragflow.svc/index", s) is True
    assert auto_worker._is_internal_target("https://a.idx.yoops.internal/x", s) is True
    assert auto_worker._is_internal_target("https://evil.com/x", s) is False
    # Fail-closed : allowlist vide → aucune cible interne.
    assert auto_worker._is_internal_target("https://ragflow.svc/x", _cfg([])) is False
    # Anti-suffixe piégé : « notragflow.svc » ne matche pas « ragflow.svc ».
    assert auto_worker._is_internal_target("https://notragflow.svc/x", s) is False


def _cfg(hosts: list[str]) -> Any:
    class C:
        trace_propagation_internal_hosts = hosts

    return C()


async def test_automate_propage_vers_interne_pas_vers_externe(
    db_pool: asyncpg.Pool, test_workspace: dict, make_block
) -> None:
    """_dispatch pose baggage+traceparent vers un hôte allowlisté, rien sinon."""
    await type_svc.create_type(db_pool, _WS, FunctionalTypeCreate(slug="epic", label="Epic"))
    event = {
        "event_code": "docflow.document.created.v1",
        "document_ref": uuid.uuid4(),
        "business": "{}",
        "correlation_id": "cid-abc",
        "correlation_kind": "document",
        "origin": "doc",
        "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    }
    prep = auto_worker._Prepared(variables={}, header_rows=[])

    captured: dict[str, dict[str, str]] = {}

    def _client(target_url: str) -> Any:
        async def request(method: str, url: str, headers: dict[str, str], **kw: Any) -> MagicMock:
            captured["headers"] = headers
            resp = MagicMock()
            resp.is_success = True
            resp.status_code = 200
            resp.text = "ok"
            return resp

        inst = AsyncMock()
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=None)
        inst.request = AsyncMock(side_effect=request)
        return inst

    async def _run(url: str, settings: Any) -> dict[str, str]:
        captured.clear()
        automation = {"id": uuid.uuid4(), "url": url, "http_method": "POST", "body_template": None}
        with (
            patch("httpx.AsyncClient", return_value=_client(url)),
            patch.object(auto_worker, "validate_public_url", AsyncMock()),
        ):
            await auto_worker._dispatch(automation, event, prep, db_pool, settings)
        return captured["headers"]

    internal = await _run("https://ragflow.svc/index", _cfg(["ragflow.svc"]))
    assert "baggage" in internal
    assert internal["traceparent"] == event["traceparent"]
    assert corr.from_headers(internal).correlation_id == "cid-abc"

    external = await _run("https://client.example.com/hook", _cfg(["ragflow.svc"]))
    assert "traceparent" not in external
    assert "baggage" not in external


async def test_webhook_ne_pose_jamais_traceparent(
    db_pool: asyncpg.Pool,
) -> None:
    """Un webhook part vers une URL cliente : jamais de traceparent, même sous
    contexte de trace ambiant (frontière externe, STANDARD §4)."""
    from cryptography.fernet import Fernet

    from docflow.schemas.webhook import WebhookCreate
    from docflow.webhooks import service as wh_svc

    key = Fernet.generate_key().decode()
    await db_pool.execute(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        "hook-corr",
        "Hook Corr",
    )
    await wh_svc.create_webhook(
        db_pool,
        "hook-corr",
        WebhookCreate(label="H", url="https://client.example.com/x", events=["document.created"]),
        encryption_key=key,
    )
    captured: dict[str, Any] = {}

    async def fake_post(url: str, **kwargs: Any) -> MagicMock:
        captured["headers"] = kwargs.get("headers", {})
        r = MagicMock()
        r.status_code = 200
        return r

    ctx = corr.CorrelationContext(
        origin="doc",
        correlation_id="c1",
        correlation_kind="document",
        traceparent="00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    )
    token = corr.bind(ctx)
    try:
        with (
            patch("httpx.AsyncClient") as MockClient,
            patch.object(wh_svc, "validate_public_url", AsyncMock()),
        ):
            inst = AsyncMock()
            inst.__aenter__ = AsyncMock(return_value=inst)
            inst.__aexit__ = AsyncMock(return_value=None)
            inst.post = AsyncMock(side_effect=fake_post)
            MockClient.return_value = inst
            snap = {"id": str(uuid.uuid4()), "title": "T", "type": "page", "version": 1}
            await wh_svc.emit_event(
                db_pool, "hook-corr", "document.created", snap, encryption_key=key
            )
    finally:
        corr.reset(token)
        await db_pool.execute("DELETE FROM workspace WHERE slug = 'hook-corr'")

    assert "traceparent" not in captured["headers"]
    assert "baggage" not in captured["headers"]

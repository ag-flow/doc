"""A1 — contrat de corrélation v1 : round-trip, opacité, relais opaque."""

from __future__ import annotations

import uuid

from docflow.observability import correlation as corr


def test_baggage_round_trip_champs_obligatoires_et_optionnels() -> None:
    ctx = corr.new_context(
        "workflow_instance", origin="workflow", step="phase-1", actor_guid="guid-42"
    )
    headers = corr.to_baggage_headers(ctx)
    assert "baggage" in headers
    back = corr.from_headers(headers)
    assert back is not None
    assert back.origin == "workflow"
    assert back.correlation_id == ctx.correlation_id
    assert back.correlation_kind == "workflow_instance"
    assert back.step == "phase-1"
    assert back.actor_guid == "guid-42"


def test_baggage_champs_optionnels_absents() -> None:
    ctx = corr.new_context("index_job")
    back = corr.from_headers(corr.to_baggage_headers(ctx))
    assert back is not None
    assert back.step is None
    assert back.actor_guid is None


def test_correlation_id_document_est_la_cle_opaque_jamais_le_titre() -> None:
    doc_key = uuid.uuid4()
    ctx = corr.new_document_context(doc_key)
    assert ctx.correlation_kind == "document"
    assert ctx.origin == corr.ORIGIN_DOC
    assert ctx.correlation_id == str(doc_key)  # UUID opaque, pas de titre/slug


def test_id_genere_est_opaque() -> None:
    a = corr.new_context("document")
    b = corr.new_context("document")
    assert a.correlation_id != b.correlation_id
    # hex uuid4 : ni titre ni slug, purement opaque
    assert len(a.correlation_id) == 32 and int(a.correlation_id, 16) >= 0


def test_relais_opaque_ne_reecrit_pas_le_fil_recu() -> None:
    incoming = corr.new_context("a2a_task", origin="a2a", correlation_id="opaque-externe-123")
    headers = corr.to_baggage_headers(incoming)
    headers["traceparent"] = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    relayed = corr.from_headers(headers)
    assert relayed is not None
    assert relayed.origin == "a2a"
    assert relayed.correlation_id == "opaque-externe-123"
    assert relayed.correlation_kind == "a2a_task"
    assert relayed.traceparent == headers["traceparent"]

    # Ré-injection interne : baggage + traceparent transportés tels quels.
    out: dict[str, str] = {}
    corr.inject_internal(out, relayed)
    assert out["traceparent"] == headers["traceparent"]
    assert corr.from_headers(out).correlation_id == "opaque-externe-123"


def test_from_headers_sans_correlation_retourne_none() -> None:
    assert corr.from_headers({}) is None
    assert corr.from_headers({"baggage": "autre=valeur"}) is None


def test_from_event_row() -> None:
    ctx = corr.from_event_row(
        {
            "correlation_id": "cid-9",
            "correlation_kind": "document",
            "origin": "doc",
            "traceparent": None,
        }
    )
    assert ctx is not None and ctx.correlation_id == "cid-9"
    assert corr.from_event_row({"correlation_id": None}) is None


def test_bind_reset_expose_et_retire_le_contexte() -> None:
    assert corr.current() is None
    ctx = corr.new_context("document")
    token = corr.bind(ctx)
    try:
        assert corr.current() is ctx
    finally:
        corr.reset(token)
    assert corr.current() is None

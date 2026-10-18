"""Fondation OBO sortant (Task 1) : relecture de `actor_guid` depuis une ligne event.

`from_event_row` reconstruit le contexte que le worker va relayer — il doit
porter l'acteur, sinon le relais OBO n'a personne à propager.
"""

from __future__ import annotations

from docflow.observability import correlation as corr


def test_from_event_row_relit_actor_guid_present() -> None:
    ctx = corr.from_event_row({"correlation_id": "c", "actor_guid": "g"})
    assert ctx is not None
    assert ctx.actor_guid == "g"


def test_from_event_row_actor_guid_absent_est_none() -> None:
    ctx = corr.from_event_row({"correlation_id": "c"})
    assert ctx is not None
    assert ctx.actor_guid is None


# ── bind_actor (Task 2 : capture de l'acteur à l'ingress MCP OBO) ──────────────


def test_bind_actor_sans_contexte_courant_cree_un_fil_document() -> None:
    assert corr.current() is None
    token = corr.bind_actor("g")
    try:
        ctx = corr.current()
        assert ctx is not None
        assert ctx.actor_guid == "g"
        assert ctx.correlation_kind == "document"
    finally:
        corr.reset(token)
    assert corr.current() is None


def test_bind_actor_avec_contexte_existant_conserve_le_correlation_id() -> None:
    existing = corr.new_context("workflow_instance", correlation_id="fil-existant")
    outer_token = corr.bind(existing)
    try:
        inner_token = corr.bind_actor("g")
        try:
            ctx = corr.current()
            assert ctx is not None
            assert ctx.correlation_id == "fil-existant"
            assert ctx.actor_guid == "g"
        finally:
            corr.reset(inner_token)
        # reset restaure l'état antérieur (sans acteur).
        restored = corr.current()
        assert restored is not None
        assert restored.actor_guid is None
        assert restored.correlation_id == "fil-existant"
    finally:
        corr.reset(outer_token)

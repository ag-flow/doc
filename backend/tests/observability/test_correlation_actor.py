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

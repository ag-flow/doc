"""Task 4b : les 3 chemins MANUELS (`service.replay_run` / `run_next_pending` /
`advance_pending`) relaient l'OBO sortant (`force_obo`), symétriquement au
worker (`tick`).

Avant ce correctif, ces 3 chemins sélectionnaient l'automate SANS `force_obo`
(donc `_dispatch` l'évaluait à False, accès défensif) et construisaient le
dict `event` SANS `actor_guid` (ni `correlation_id`) : un automate
`force_obo=True` rejoué/avancé à la main émettait quand même, sous le Bearer
de service, SANS en-têtes OBO — brèche d'isolation (fail-open).

Trois scénarios (mêmes critères d'acceptation que `test_worker_obo.py`,
rejoués via les points d'entrée manuels) :

- (a) `force_obo=True`, acteur connu + Bearer configuré → les 3 en-têtes OBO
  sont posés, vérification HMAC locale (sans importer `rag`).
- (b) `force_obo=True` mais acteur ABSENT (event non corrélé) → `defer`,
  aucun appel HTTP, sous aucun Bearer.
- (c) `force_obo=False` → comportement inchangé, aucun en-tête OBO même avec
  acteur connu et Bearer configuré.

Couvre les 3 fonctions : (a) et (b) via `replay_run` (chemin le plus simple à
amorcer : un `automation_run` + son `document_event` déjà en base, pas de
filtre à satisfaire), (a) aussi via `run_next_pending`, (c) via
`advance_pending` — pour que les 3 points d'entrée soient exercés.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import asyncpg
import pytest

from docflow.automations import service as auto_svc
from docflow.automations import worker

_CREATED = "docflow.block.created.v1"
_URL = "https://relay.example/hook"


class _Resp:
    def __init__(self, status: int = 201, text: str = '{"ok": true}') -> None:
        self.status_code = status
        self.is_success = 200 <= status < 300
        self.text = text


class _FakeClient:
    """Capture chaque appel (méthode, URL, en-têtes) — jamais de vrai réseau."""

    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *a: Any) -> bool:
        return False

    async def request(
        self, method: str, url: str, headers: Any = None, content: Any = None
    ) -> _Resp:
        _CALLS.append({"method": method, "url": url, "headers": dict(headers or {})})
        return _Resp()


_CALLS: list[dict[str, Any]] = []


class _Settings:
    public_base_url = "https://doc.example"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _CALLS.clear()
    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeClient)

    async def _noop(url: str) -> None:
        return None

    monkeypatch.setattr(worker, "validate_public_url", _noop)


async def _automation(
    pool: asyncpg.Pool, *, force_obo: bool, bearer_secret_value: str | None
) -> tuple[uuid.UUID, uuid.UUID]:
    """Un automate persisté (workspace, header Bearer optionnel). Retourne
    (automation_id, workspace_technical_key)."""
    slug = f"man-obo-{uuid.uuid4().hex[:8]}"
    wk: uuid.UUID = await pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) RETURNING workspace_technical_key",
        slug,
        "Manuel OBO",
    )
    auto_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "url, http_method, force_obo) "
        "VALUES ($1, $2, true, $3, $4, $5, $6) RETURNING id",
        wk,
        "Relais OBO manuel",
        [_CREATED],
        _URL,
        "POST",
        force_obo,
    )
    if bearer_secret_value is not None:
        await pool.execute(
            "INSERT INTO automation_header (automation_ref, name, value, value_prefix, enabled) "
            "VALUES ($1, 'Authorization', $2, 'Bearer ', true)",
            auto_id,
            bearer_secret_value,
        )
    return auto_id, wk


async def _event_with_run(
    pool: asyncpg.Pool, automation_id: uuid.UUID, wk: uuid.UUID, *, actor_guid: str | None
) -> uuid.UUID:
    """Un `document_event` corrélé + son `automation_run` (status=failed,
    prêt à être rejoué) : exactement le point de départ de `replay_run`.

    `correlation_id` toujours posé (comme en production, cf.
    `CorrelationContext` — jamais vide quand l'event est journalisé par une
    mutation réelle) : seul `actor_guid` varie selon le scénario.
    """
    seq: int = await pool.fetchval(
        "INSERT INTO document_event "
        "(workspace_technical_key, document_ref, event_code, business, "
        " correlation_id, correlation_kind, origin, actor_guid) "
        "VALUES ($1, NULL, $2, $3::jsonb, $4, 'document', 'doc', $5) RETURNING seq",
        wk,
        _CREATED,
        json.dumps({}),
        f"corr-{uuid.uuid4().hex[:8]}",
        actor_guid,
    )
    run_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO automation_run "
        "(automation_ref, document_ref, document_version, change_log_seq, event_seq, "
        " status, event_code, manual) "
        "VALUES ($1, NULL, NULL, $2, $2, 'failed', $3, true) RETURNING id",
        automation_id,
        seq,
        _CREATED,
    )
    return run_id


async def test_replay_run_force_obo_avec_acteur_et_bearer_pose_les_3_entetes(
    db_pool: asyncpg.Pool,
) -> None:
    actor = "11111111-2222-3333-4444-555555555555"
    auto_id, wk = await _automation(db_pool, force_obo=True, bearer_secret_value="s3cr3t")
    run_id = await _event_with_run(db_pool, auto_id, wk, actor_guid=actor)

    before = time.time()
    out = await auto_svc.replay_run(db_pool, None, auto_id, run_id, _Settings())
    after = time.time()

    assert out.status == "ok", "pas de defer : acteur ET Bearer présents"
    assert len(_CALLS) == 1
    headers = _CALLS[0]["headers"]

    assert headers["x-portal-actor"] == actor
    ts = int(headers["x-portal-actor-timestamp"])
    assert before - 1 <= ts <= after + 1
    expected_sig = hmac.new(b"s3cr3t", f"{actor}\n{ts}".encode(), hashlib.sha256).hexdigest()
    assert headers["x-portal-actor-signature"] == expected_sig
    assert headers["Authorization"] == "Bearer s3cr3t"


async def test_replay_run_force_obo_sans_acteur_differe_sans_appel(
    db_pool: asyncpg.Pool,
) -> None:
    auto_id, wk = await _automation(db_pool, force_obo=True, bearer_secret_value="s3cr3t")
    run_id = await _event_with_run(db_pool, auto_id, wk, actor_guid=None)

    out = await auto_svc.replay_run(db_pool, None, auto_id, run_id, _Settings())

    assert _CALLS == [], "fail-closed : aucun appel au nom de personne"
    assert out.status == "defer"


async def test_run_next_pending_force_obo_avec_acteur_pose_les_3_entetes(
    db_pool: asyncpg.Pool,
) -> None:
    actor = "66666666-7777-8888-9999-000000000000"
    auto_id, wk = await _automation(db_pool, force_obo=True, bearer_secret_value="s3cr3t")
    # Portée restreinte à SON workspace : sinon l'automate ramasserait aussi
    # les events laissés par d'autres tests (données partagées pour la durée
    # de la session), rendant le résultat dépendant de l'ordre d'exécution.
    await db_pool.execute(
        "INSERT INTO automation_workspace (automation_ref, workspace_technical_key) "
        "VALUES ($1, $2)",
        auto_id,
        wk,
    )
    await db_pool.execute(
        "INSERT INTO document_event "
        "(workspace_technical_key, document_ref, event_code, business, "
        " correlation_id, correlation_kind, origin, actor_guid) "
        "VALUES ($1, NULL, $2, $3::jsonb, $4, 'document', 'doc', $5)",
        wk,
        _CREATED,
        json.dumps({}),
        f"corr-{uuid.uuid4().hex[:8]}",
        actor,
    )

    res = await auto_svc.run_next_pending(db_pool, None, auto_id, _Settings())

    assert res["status"] == "ok"
    assert len(_CALLS) == 1
    headers = _CALLS[0]["headers"]
    assert headers["x-portal-actor"] == actor
    assert headers["Authorization"] == "Bearer s3cr3t"


async def test_advance_pending_force_obo_false_inchange(db_pool: asyncpg.Pool) -> None:
    """Non-régression : `force_obo=False` n'ajoute RIEN, même avec un Bearer
    configuré et un acteur journalisé sur l'event."""
    actor = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    auto_id, wk = await _automation(db_pool, force_obo=False, bearer_secret_value="s3cr3t")
    await db_pool.execute(
        "INSERT INTO automation_workspace (automation_ref, workspace_technical_key) "
        "VALUES ($1, $2)",
        auto_id,
        wk,
    )
    await db_pool.execute(
        "INSERT INTO document_event "
        "(workspace_technical_key, document_ref, event_code, business, "
        " correlation_id, correlation_kind, origin, actor_guid) "
        "VALUES ($1, NULL, $2, $3::jsonb, $4, 'document', 'doc', $5)",
        wk,
        _CREATED,
        json.dumps({}),
        f"corr-{uuid.uuid4().hex[:8]}",
        actor,
    )

    res = await auto_svc.advance_pending(db_pool, None, auto_id, _Settings())

    assert res["status"] == "ok"
    assert res["advanced"] is True
    assert len(_CALLS) == 1
    headers = _CALLS[0]["headers"]
    assert "x-portal-actor" not in headers
    assert "x-portal-actor-timestamp" not in headers
    assert "x-portal-actor-signature" not in headers
    assert headers["Authorization"] == "Bearer s3cr3t"

"""`force_obo` câblé dans `_dispatch` — relais d'identité ou defer fail-closed.

Trois scénarios (chantier OBO sortant, Task 4) :

- (a) `force_obo=True`, acteur connu (actor_guid) ET secret porteur (header
  `Authorization: Bearer`) → les 3 en-têtes OBO sont posés, signature
  vérifiable localement (sans importer `rag` — réimplémentation du HMAC).
- (b) `force_obo=True` mais acteur ABSENT → AUCUN appel HTTP, `ExecResult`
  `defer` : fail-closed, jamais un appel « au nom de personne ».
- (c) `force_obo=False` → comportement inchangé (régression nulle), aucun
  en-tête OBO posé même si un header Bearer est configuré.

Testé au niveau `_dispatch`/`_prepare` directement (pas `run_tick`) : l'event
est construit à la main avec son `actor_guid`, exactement comme le fait
`corr.from_event_row` en production une fois le journal `document_event`
plumbé jusqu'au dict `event` du worker — ce qui est hors du périmètre de
cette tâche (voir le rapport).

Placé à plat (`tests/test_worker_*.py`), comme le reste des tests d'automates.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from typing import Any

import asyncpg
import pytest

from docflow.automations import worker

_CREATED = "docflow.block.created.v1"
_URL = "https://relay.example/hook"

_COLS = (
    "SELECT id, workspace_technical_key, url, http_method, body_template, force_obo "
    "FROM automation WHERE id = $1"
)


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
) -> uuid.UUID:
    """Un automate persisté, avec ou sans header `Authorization: Bearer`.

    Le header est écrit en deux colonnes (`value` + `value_prefix`) exactement
    comme le ferait l'écran d'édition : la valeur résolue au dispatch est
    `value_prefix + value`, ici `"Bearer " + bearer_secret_value`.
    """
    slug = f"obo-{uuid.uuid4().hex[:8]}"
    wk: uuid.UUID = await pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) RETURNING workspace_technical_key",
        slug,
        "OBO worker",
    )
    auto_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "url, http_method, force_obo) "
        "VALUES ($1, $2, true, $3, $4, $5, $6) RETURNING id",
        wk,
        "Relais OBO",
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
    return auto_id


def _event(*, actor_guid: str | None, correlation_id: str | None = "corr-1") -> dict[str, Any]:
    return {
        "event_code": _CREATED,
        "document_ref": None,
        "business": {},
        "correlation_id": correlation_id,
        "correlation_kind": "document",
        "origin": "doc",
        "traceparent": None,
        "actor_guid": actor_guid,
    }


async def test_force_obo_avec_acteur_et_bearer_pose_les_3_entetes(db_pool: asyncpg.Pool) -> None:
    auto_id = await _automation(db_pool, force_obo=True, bearer_secret_value="s3cr3t")
    automation = await db_pool.fetchrow(_COLS, auto_id)
    async with db_pool.acquire() as conn:
        prep = await worker._prepare(conn, automation, _event(actor_guid=None), _Settings())

    before = time.time()
    res = await worker._dispatch(automation, _event(actor_guid="g"), prep, db_pool, _Settings())
    after = time.time()

    assert res.status == "ok"
    assert len(_CALLS) == 1, "l'appel principal doit bien partir"
    headers = _CALLS[0]["headers"]

    assert headers["x-portal-actor"] == "g"
    ts = int(headers["x-portal-actor-timestamp"])
    assert before - 1 <= ts <= after + 1, "timestamp = instant du dispatch, pas de l'event"

    # Vérif HMAC LOCALE (sans importer `rag` — couplage interdit) : la
    # signature doit être reproductible avec le secret du header Bearer.
    expected_sig = hmac.new(b"s3cr3t", f"g\n{ts}".encode(), hashlib.sha256).hexdigest()
    assert headers["x-portal-actor-signature"] == expected_sig

    # L'en-tête Authorization original (porteur du secret) part toujours tel
    # quel : l'OBO s'AJOUTE, il ne remplace pas l'authentification de
    # l'automate vers sa cible.
    assert headers["Authorization"] == "Bearer s3cr3t"


async def test_force_obo_sans_acteur_ne_part_pas_et_differe(db_pool: asyncpg.Pool) -> None:
    auto_id = await _automation(db_pool, force_obo=True, bearer_secret_value="s3cr3t")
    automation = await db_pool.fetchrow(_COLS, auto_id)
    async with db_pool.acquire() as conn:
        prep = await worker._prepare(conn, automation, _event(actor_guid=None), _Settings())

    res = await worker._dispatch(automation, _event(actor_guid=None), prep, db_pool, _Settings())

    assert _CALLS == [], "fail-closed : aucun appel au nom de personne"
    assert res.status == "defer", "ni ok, ni failed : ni dead-letter, ni appel"


async def test_force_obo_sans_bearer_configure_ne_part_pas_et_differe(
    db_pool: asyncpg.Pool,
) -> None:
    """Acteur connu MAIS aucun secret porteur (pas de header Bearer) : même
    garde que l'absence d'acteur — il faut les DEUX pour relayer."""
    auto_id = await _automation(db_pool, force_obo=True, bearer_secret_value=None)
    automation = await db_pool.fetchrow(_COLS, auto_id)
    async with db_pool.acquire() as conn:
        prep = await worker._prepare(conn, automation, _event(actor_guid=None), _Settings())

    res = await worker._dispatch(automation, _event(actor_guid="g"), prep, db_pool, _Settings())

    assert _CALLS == []
    assert res.status == "defer"


async def test_force_obo_false_appelle_sans_entetes_obo(db_pool: asyncpg.Pool) -> None:
    """Non-régression : `force_obo=False` n'ajoute RIEN, même avec un Bearer
    configuré et un acteur connu sur l'event."""
    auto_id = await _automation(db_pool, force_obo=False, bearer_secret_value="s3cr3t")
    automation = await db_pool.fetchrow(_COLS, auto_id)
    async with db_pool.acquire() as conn:
        prep = await worker._prepare(conn, automation, _event(actor_guid=None), _Settings())

    res = await worker._dispatch(automation, _event(actor_guid="g"), prep, db_pool, _Settings())

    assert res.status == "ok"
    assert len(_CALLS) == 1
    headers = _CALLS[0]["headers"]
    assert "x-portal-actor" not in headers
    assert "x-portal-actor-timestamp" not in headers
    assert "x-portal-actor-signature" not in headers
    assert headers["Authorization"] == "Bearer s3cr3t"


async def test_automation_sans_colonne_force_obo_est_traitee_comme_false(
    db_pool: asyncpg.Pool,
) -> None:
    """Les appelants manuels (`replay_run`, `run_next_pending`…) sélectionnent
    l'automate SANS la colonne `force_obo` : `_dispatch` ne doit pas lever de
    KeyError, et doit se comporter comme `force_obo=False`."""
    auto_id = await _automation(db_pool, force_obo=True, bearer_secret_value="s3cr3t")
    automation = await db_pool.fetchrow(
        "SELECT id, workspace_technical_key, url, http_method, body_template "
        "FROM automation WHERE id = $1",
        auto_id,
    )
    async with db_pool.acquire() as conn:
        prep = await worker._prepare(conn, automation, _event(actor_guid=None), _Settings())

    res = await worker._dispatch(automation, _event(actor_guid="g"), prep, db_pool, _Settings())

    assert res.status == "ok"
    headers = _CALLS[0]["headers"]
    assert "x-portal-actor" not in headers


async def test_run_tick_force_obo_sans_acteur_gele_le_curseur_sans_dead_letter(
    db_pool: asyncpg.Pool,
) -> None:
    """Bout en bout via `run_tick` : un event réel (sans actor_guid, comme
    aujourd'hui tout event journalisé) sur un automate `force_obo=True` ne
    doit ni appeler, ni dead-letter, ni avancer le curseur."""
    import json

    slug = f"obo-tick-{uuid.uuid4().hex[:8]}"
    wk: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) RETURNING workspace_technical_key",
        slug,
        "OBO tick",
    )
    seq: int = await db_pool.fetchval(
        "INSERT INTO document_event (workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1, NULL, $2, $3::jsonb) RETURNING seq",
        wk,
        _CREATED,
        json.dumps({}),
    )
    auto_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "url, http_method, force_obo) VALUES ($1, $2, true, $3, $4, $5, true) RETURNING id",
        wk,
        "Relais OBO tick",
        [_CREATED],
        _URL,
        "POST",
    )
    await db_pool.execute(
        "INSERT INTO automation_header (automation_ref, name, value, value_prefix, enabled) "
        "VALUES ($1, 'Authorization', 's3cr3t', 'Bearer ', true)",
        auto_id,
    )
    # Portée restreinte à SON workspace : sinon l'automate ramasserait aussi
    # les events (avec actor_guid) d'autres tests, qui émettraient et
    # fausseraient l'assertion `_CALLS == []`. Isolation, pas de dépendance à
    # l'ordre.
    await db_pool.execute(
        "INSERT INTO automation_workspace (automation_ref, workspace_technical_key) "
        "VALUES ($1, $2)",
        auto_id,
        wk,
    )
    automation = await db_pool.fetchrow(
        "SELECT id, workspace_technical_key, event_codes, block_slugs, block_templates, "
        "stop_chain, functional_type_slugs, delay_minutes, url, http_method, body_template, "
        "precheck, force_obo FROM automation WHERE id = $1",
        auto_id,
    )

    await worker.run_tick(db_pool, automation, _Settings())

    assert _CALLS == [], "l'event journalisé (sans actor_guid) : defer, aucun appel"
    run = await db_pool.fetchrow(
        "SELECT status FROM automation_run WHERE automation_ref=$1 AND event_seq=$2",
        auto_id,
        seq,
    )
    assert run is None, "différer n'est pas un échec : aucun run n'est enregistré"
    cursor = await db_pool.fetchval(
        "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1", auto_id
    )
    assert cursor is None, "le curseur reste gelé : l'event sera retenté, pas de dead-letter"


async def test_run_tick_force_obo_avec_actor_guid_journalise_emet_les_entetes(
    db_pool: asyncpg.Pool,
) -> None:
    """Bout en bout, PONT FERMÉ : un `document_event` écrit AVEC `actor_guid`
    est relu par `matching_batch`, traverse `from_event_row`, et le dispatch
    pose réellement les 3 en-têtes OBO — PAS de defer.

    C'est la preuve que la chaîne SQL → dict event → `ctx.actor_guid` est
    complète : le test NULL ci-dessus prouve le fail-closed, celui-ci prouve
    l'émission. Sans le report de `de.actor_guid` dans les deux SELECT de
    `events_query` ET dans le dict event de `_process_event`, il différerait.
    """
    import json

    actor = "11111111-2222-3333-4444-555555555555"
    slug = f"obo-emit-{uuid.uuid4().hex[:8]}"
    wk: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) RETURNING workspace_technical_key",
        slug,
        "OBO emit",
    )
    # correlation_id non nul : `from_event_row` ne reconstruit un contexte (et
    # donc ne porte `actor_guid`) que si l'event est corrélé.
    seq: int = await db_pool.fetchval(
        "INSERT INTO document_event "
        "(workspace_technical_key, document_ref, event_code, business, "
        " correlation_id, correlation_kind, origin, actor_guid) "
        "VALUES ($1, NULL, $2, $3::jsonb, $4, 'document', 'doc', $5) RETURNING seq",
        wk,
        _CREATED,
        json.dumps({}),
        "corr-emit-1",
        actor,
    )
    auto_id: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "url, http_method, force_obo) VALUES ($1, $2, true, $3, $4, $5, true) RETURNING id",
        wk,
        "Relais OBO emit",
        [_CREATED],
        _URL,
        "POST",
    )
    await db_pool.execute(
        "INSERT INTO automation_header (automation_ref, name, value, value_prefix, enabled) "
        "VALUES ($1, 'Authorization', 's3cr3t', 'Bearer ', true)",
        auto_id,
    )
    # Portée restreinte à SON workspace : sans scope, l'automate ramasserait
    # aussi les events (sans actor_guid) laissés par les autres tests de la
    # session, dont le defer gèlerait le curseur — le test deviendrait
    # dépendant de l'ordre d'exécution.
    await db_pool.execute(
        "INSERT INTO automation_workspace (automation_ref, workspace_technical_key) "
        "VALUES ($1, $2)",
        auto_id,
        wk,
    )
    automation = await db_pool.fetchrow(
        "SELECT id, workspace_technical_key, event_codes, block_slugs, block_templates, "
        "stop_chain, functional_type_slugs, delay_minutes, url, http_method, body_template, "
        "precheck, force_obo FROM automation WHERE id = $1",
        auto_id,
    )

    before = time.time()
    await worker.run_tick(db_pool, automation, _Settings())
    after = time.time()

    emitted = [c for c in _CALLS if c["url"] == _URL]
    assert len(emitted) == 1, "l'appel principal doit partir : plus de defer"
    headers = emitted[0]["headers"]
    assert headers["x-portal-actor"] == actor
    ts = int(headers["x-portal-actor-timestamp"])
    assert before - 1 <= ts <= after + 1
    expected_sig = hmac.new(b"s3cr3t", f"{actor}\n{ts}".encode(), hashlib.sha256).hexdigest()
    assert headers["x-portal-actor-signature"] == expected_sig
    assert headers["Authorization"] == "Bearer s3cr3t"

    run = await db_pool.fetchrow(
        "SELECT status FROM automation_run WHERE automation_ref=$1 AND event_seq=$2",
        auto_id,
        seq,
    )
    assert run is not None and run["status"] == "ok", "l'appel a eu lieu : run enregistré"
    cursor = await db_pool.fetchval(
        "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1", auto_id
    )
    assert cursor == seq, "l'event est traité : le curseur avance"

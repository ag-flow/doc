"""Automates déclenchés par les EVENTS (journal document_event).

Couvre : (1) outbox.enqueue écrit document_event même producteur désactivé ;
(2) le worker consomme les events filtrés par event_codes, substitue le contenu
du document ET les propriétés de l'event, enregistre le run et dédup.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import pytest

from docflow.automations import worker
from docflow.events import outbox

_UPDATED = "docflow.document.updated.v1"
_CREATED = "docflow.document.created.v1"


class _FakeResp:
    status_code = 200
    is_success = True
    text = '{"ok": true}'


class _FakeClient:
    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *a: Any) -> bool:
        return False

    async def request(
        self, method: str, url: str, headers: Any = None, content: Any = None
    ) -> _FakeResp:
        _CALLS.append({"method": method, "url": url, "headers": headers, "content": content})
        return _FakeResp()


_CALLS: list[dict[str, Any]] = []


async def _mk_ws_doc(pool: asyncpg.Pool) -> tuple[uuid.UUID, str, uuid.UUID]:
    slug = f"auto-ev-{uuid.uuid4().hex[:8]}"
    wk = await pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) RETURNING workspace_technical_key",
        slug,
        "Auto Ev",
    )
    ft = await pool.fetchval(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ($1,$2,$3) RETURNING id",
        "t",
        "T",
        wk,
    )
    block = await pool.fetchval(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1,$2,$3,$4) RETURNING id",
        "b",
        "B",
        ft,
        wk,
    )
    doc_id = await pool.fetchval(
        "INSERT INTO document (workspace_technical_key, data_block_ref, functional_type_ref, "
        "title, version) VALUES ($1,$2,$3,$4,1) RETURNING doc_technical_key",
        wk,
        block,
        ft,
        "Titre doc",
    )
    await pool.execute(
        "INSERT INTO document_version (document_ref, version_number, title, content) "
        "VALUES ($1, 1, $2, $3)",
        doc_id,
        "Titre doc",
        "Contenu du doc",
    )
    return wk, slug, doc_id


async def test_enqueue_records_document_event_even_when_producer_disabled(
    db_pool: asyncpg.Pool,
) -> None:
    outbox.configure(enabled=False, source="docflow", allowed_events=None)
    wk, _slug, doc_id = await _mk_ws_doc(db_pool)
    before = await db_pool.fetchval("SELECT count(*) FROM document_event")
    async with db_pool.acquire() as conn, conn.transaction():
        await outbox.enqueue(
            conn,
            event_code=_UPDATED,
            workspace_wk=wk,
            business={"documentId": str(doc_id), "workspaceSlug": _slug, "version": 2},
        )
    after = await db_pool.fetchval("SELECT count(*) FROM document_event")
    assert after == before + 1
    row = await db_pool.fetchrow(
        "SELECT event_code, document_ref, business FROM document_event "
        "WHERE document_ref = $1 ORDER BY seq DESC LIMIT 1",
        doc_id,
    )
    assert row["event_code"] == _UPDATED
    biz = json.loads(row["business"]) if isinstance(row["business"], str) else row["business"]
    assert biz["workspaceSlug"] == _slug


async def test_worker_triggers_on_event_with_variables_and_dedup(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    _CALLS.clear()
    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeClient)

    async def _noop(url: str) -> None:
        return None

    monkeypatch.setattr(worker, "validate_public_url", _noop)

    wk, slug, doc_id = await _mk_ws_doc(db_pool)

    # Un event 'updated' pour ce document.
    await db_pool.execute(
        "INSERT INTO document_event (workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1,$2,$3,$4::jsonb)",
        wk,
        doc_id,
        _UPDATED,
        json.dumps({"documentId": str(doc_id), "workspaceSlug": slug, "version": 3}),
    )
    # Un event 'created' NON sélectionné → ne doit pas déclencher.
    await db_pool.execute(
        "INSERT INTO document_event (workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1,$2,$3,$4::jsonb)",
        wk,
        doc_id,
        _CREATED,
        json.dumps({"documentId": str(doc_id), "workspaceSlug": slug}),
    )

    auto_id = await db_pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "delay_minutes, url, http_method, body_template) "
        "VALUES ($1,$2,true,$3,0,$4,$5,$6) RETURNING id",
        wk,
        "RAG",
        [_UPDATED],
        "https://rag.example/index",
        "POST",
        json.dumps(
            {
                "doc": "{content}",
                "ws": "{event.workspaceSlug}",
                "v": "{event.version}",
                "url": "{doc_url}",
                "dtype": "{doc_type}",
            }
        ),
    )
    await db_pool.execute(
        "INSERT INTO automation_workspace (automation_ref, workspace_technical_key) "
        "VALUES ($1, $2) ON CONFLICT DO NOTHING",
        auto_id, wk,
    )

    automation = await db_pool.fetchrow(
        "SELECT id, workspace_technical_key, event_codes, block_slugs, functional_type_slugs, "
        "stop_chain, "
        "delay_minutes, url, http_method, "
        "body_template FROM automation WHERE id = $1",
        auto_id,
    )

    class _Settings:
        public_base_url = "https://doc.example"

    await worker.run_tick(db_pool, automation, _Settings())

    # Un seul appel (updated), pas created.
    assert len(_CALLS) == 1
    body = json.loads(_CALLS[0]["content"].decode())
    assert body["doc"] == "Contenu du doc"       # {content} substitué
    assert body["ws"] == slug                     # {event.workspaceSlug} substitué
    assert body["v"] == "3"                       # {event.version} substitué (str)
    # {doc_url} = URL de consultation absolue (public_base_url + chemin app).
    assert body["url"] == f"https://doc.example/ws/{slug}/blocs/b/documents/{doc_id}"
    assert body["dtype"] == "md"                  # {doc_type} substitué (défaut md)

    # Un run enregistré, statut ok.
    runs = await db_pool.fetch(
        "SELECT status, event_seq FROM automation_run WHERE automation_ref = $1", auto_id
    )
    assert len(runs) == 1
    assert runs[0]["status"] == "ok"

    # Dédup : rejouer le tick ne refait pas l'appel.
    await worker.run_tick(db_pool, automation, object())
    assert len(_CALLS) == 1


async def test_run_next_does_not_advance_cursor(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from docflow.automations import service as auto_svc

    _CALLS.clear()
    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeClient)

    async def _noop(url: str) -> None:
        return None

    monkeypatch.setattr(worker, "validate_public_url", _noop)

    wk, slug, doc_id = await _mk_ws_doc(db_pool)
    for _ in range(2):
        await db_pool.execute(
            "INSERT INTO document_event "
            "(workspace_technical_key, document_ref, event_code, business) "
            "VALUES ($1,$2,$3,$4::jsonb)",
            wk, doc_id, _UPDATED, json.dumps({"documentId": str(doc_id), "workspaceSlug": slug}),
        )
    auto_id = await db_pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "delay_minutes, url, http_method, body_template) "
        "VALUES ($1,'RAG',false,$2,0,$3,'POST',null) RETURNING id",
        wk, [_UPDATED], "https://rag.example/index",
    )
    await db_pool.execute(
        "INSERT INTO automation_workspace (automation_ref, workspace_technical_key) "
        "VALUES ($1, $2) ON CONFLICT DO NOTHING",
        auto_id, wk,
    )

    autos = await auto_svc.list_automations(db_pool, slug)
    a = next(x for x in autos if x.id == auto_id)
    assert a.pending_count == 2
    assert a.active is False

    res = await auto_svc.run_next_pending(db_pool, slug, auto_id, object())
    assert res["status"] == "ok"
    assert len(_CALLS) == 1  # un seul appel (le 1er event en attente)

    # Curseur NON avancé → toujours 2 en attente.
    autos2 = await auto_svc.list_automations(db_pool, slug)
    assert next(x for x in autos2 if x.id == auto_id).pending_count == 2

    # Mais l'appel unitaire EST historisé (run manuel, event_seq NULL → pas de dédup).
    run = await db_pool.fetchrow(
        "SELECT manual, event_seq, status FROM automation_run WHERE automation_ref = $1", auto_id
    )
    assert run is not None
    assert run["manual"] is True
    assert run["event_seq"] is None
    assert run["status"] == "ok"


async def test_run_records_detail_and_prunes_to_20(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    _CALLS.clear()
    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeClient)

    async def _noop(url: str) -> None:
        return None

    monkeypatch.setattr(worker, "validate_public_url", _noop)

    wk, slug, doc_id = await _mk_ws_doc(db_pool)
    # 25 events 'updated' → 25 runs, purgés à 20.
    for _ in range(25):
        await db_pool.execute(
            "INSERT INTO document_event "
            "(workspace_technical_key, document_ref, event_code, business) "
            "VALUES ($1,$2,$3,$4::jsonb)",
            wk, doc_id, _UPDATED, json.dumps({"documentId": str(doc_id), "workspaceSlug": slug}),
        )
    auto_id = await db_pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "delay_minutes, url, http_method, body_template) "
        "VALUES ($1,'RAG',true,$2,0,$3,'POST',$4) RETURNING id",
        wk, [_UPDATED], "https://rag.example/index", json.dumps({"doc": "{content}"}),
    )
    await db_pool.execute(
        "INSERT INTO automation_workspace (automation_ref, workspace_technical_key) "
        "VALUES ($1, $2) ON CONFLICT DO NOTHING",
        auto_id, wk,
    )
    automation = await db_pool.fetchrow(
        "SELECT id, workspace_technical_key, event_codes, block_slugs, functional_type_slugs, "
        "stop_chain, "
        "delay_minutes, url, http_method, "
        "body_template FROM automation WHERE id = $1",
        auto_id,
    )
    await worker.run_tick(db_pool, automation, object())

    # Purge : seuls les 20 plus récents restent.
    assert await db_pool.fetchval(
        "SELECT count(*) FROM automation_run WHERE automation_ref = $1", auto_id
    ) == 20

    # Le dernier run porte le détail : corps envoyé (résolu), réponse, code, event.
    r = await db_pool.fetchrow(
        "SELECT status, http_status, request_body, response_body, event_code, url "
        "FROM automation_run WHERE automation_ref = $1 ORDER BY executed_at DESC LIMIT 1",
        auto_id,
    )
    assert r["status"] == "ok"
    assert r["http_status"] == 200
    assert r["event_code"] == _UPDATED
    assert r["url"] == "https://rag.example/index"
    assert "Contenu du doc" in r["request_body"]   # {content} résolu
    assert "ok" in r["response_body"]               # corps de réponse (_FakeResp.text)


async def test_advance_and_cursor_back(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from docflow.automations import service as auto_svc

    _CALLS.clear()
    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeClient)

    async def _noop(url: str) -> None:
        return None

    monkeypatch.setattr(worker, "validate_public_url", _noop)

    wk, slug, doc_id = await _mk_ws_doc(db_pool)
    seqs: list[int] = []
    for _ in range(2):
        s = await db_pool.fetchval(
            "INSERT INTO document_event "
            "(workspace_technical_key, document_ref, event_code, business) "
            "VALUES ($1,$2,$3,$4::jsonb) RETURNING seq",
            wk, doc_id, _UPDATED, json.dumps({"documentId": str(doc_id), "workspaceSlug": slug}),
        )
        seqs.append(s)
    auto_id = await db_pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "delay_minutes, url, http_method, body_template) "
        "VALUES ($1,'RAG',false,$2,0,$3,'POST',null) RETURNING id",
        wk, [_UPDATED], "https://rag.example/index",
    )
    await db_pool.execute(
        "INSERT INTO automation_workspace (automation_ref, workspace_technical_key) "
        "VALUES ($1, $2) ON CONFLICT DO NOTHING",
        auto_id, wk,
    )

    async def _pending() -> int:
        autos = await auto_svc.list_automations(db_pool, slug)
        return next(x for x in autos if x.id == auto_id).pending_count

    assert await _pending() == 2

    # Advance : joue le 1er event, l'historise (event_seq, manual=false), avance le curseur.
    r = await auto_svc.advance_pending(db_pool, slug, auto_id, object())
    assert r["status"] == "ok" and r["advanced"] is True
    assert await _pending() == 1
    run = await db_pool.fetchrow(
        "SELECT manual, event_seq FROM automation_run WHERE event_seq = $1", seqs[0]
    )
    assert run is not None and run["manual"] is False

    # Back : recule le curseur → le 1er event redevient en attente.
    await auto_svc.cursor_back(db_pool, slug, auto_id)
    assert await _pending() == 2


async def test_block_filter_and(db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch) -> None:
    from docflow.automations import service as auto_svc

    _CALLS.clear()
    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeClient)

    async def _noop(url: str) -> None:
        return None

    monkeypatch.setattr(worker, "validate_public_url", _noop)

    wk, slug, doc_id = await _mk_ws_doc(db_pool)  # document dans le bloc 'b', type 't'
    await db_pool.execute(
        "INSERT INTO document_event "
        "(workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1,$2,$3,$4::jsonb)",
        wk, doc_id, _UPDATED, json.dumps({"documentId": str(doc_id), "workspaceSlug": slug}),
    )
    # Filtre sur un AUTRE bloc → l'event ne matche pas.
    auto_id = await db_pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "block_slugs, delay_minutes, url, http_method) "
        "VALUES ($1,'RAG',true,$2,ARRAY['autre-bloc'],0,$3,'POST') RETURNING id",
        wk, [_UPDATED], "https://rag.example/index",
    )
    await db_pool.execute(
        "INSERT INTO automation_workspace (automation_ref, workspace_technical_key) "
        "VALUES ($1, $2) ON CONFLICT DO NOTHING",
        auto_id, wk,
    )

    async def _pending() -> int:
        autos = await auto_svc.list_automations(db_pool, slug)
        return next(x for x in autos if x.id == auto_id).pending_count

    assert await _pending() == 0  # bloc 'b' ∉ ['autre-bloc']

    # On filtre sur le BON bloc → matche.
    await db_pool.execute(
        "UPDATE automation SET block_slugs = ARRAY['b'] WHERE id = $1", auto_id
    )
    assert await _pending() == 1

    automation = await db_pool.fetchrow(
        "SELECT id, workspace_technical_key, event_codes, block_slugs, functional_type_slugs, "
        "stop_chain, "
        "delay_minutes, url, http_method, body_template FROM automation WHERE id = $1",
        auto_id,
    )
    await worker.run_tick(db_pool, automation, object())
    assert len(_CALLS) == 1


async def test_multi_workspace_scope(db_pool: asyncpg.Pool) -> None:
    from fastapi import HTTPException

    from docflow.automations import service as auto_svc
    from docflow.schemas.automations import AutomationCreate, AutomationUpdate

    wk_a, slug_a, doc_a = await _mk_ws_doc(db_pool)
    wk_b, slug_b, doc_b = await _mk_ws_doc(db_pool)

    out = await auto_svc.create_automation(
        db_pool,
        slug_a,
        AutomationCreate(
            label="Multi", event_codes=[_UPDATED],
            workspace_slugs=[slug_a, slug_b],
            url="https://rag.example/index", http_method="POST",
        ),
    )
    assert sorted(out.workspace_slugs) == sorted([slug_a, slug_b])

    # Visible dans les DEUX workspaces cochés.
    assert any(a.id == out.id for a in await auto_svc.list_automations(db_pool, slug_a))
    assert any(a.id == out.id for a in await auto_svc.list_automations(db_pool, slug_b))

    # Les events des deux workspaces comptent dans le pending.
    for wk, doc in [(wk_a, doc_a), (wk_b, doc_b)]:
        await db_pool.execute(
            "INSERT INTO document_event "
            "(workspace_technical_key, document_ref, event_code, business) "
            "VALUES ($1,$2,$3,$4::jsonb)",
            wk, doc, _UPDATED, json.dumps({"documentId": str(doc)}),
        )
    a = next(x for x in await auto_svc.list_automations(db_pool, slug_a) if x.id == out.id)
    assert a.pending_count == 2

    # Restreindre à B : plus visible dans A, toujours dans B.
    await auto_svc.update_automation(
        db_pool, slug_a, out.id, AutomationUpdate(workspace_slugs=[slug_b])
    )
    assert not any(x.id == out.id for x in await auto_svc.list_automations(db_pool, slug_a))
    assert any(x.id == out.id for x in await auto_svc.list_automations(db_pool, slug_b))

    # Jamais aucun workspace → 422.
    with pytest.raises(HTTPException) as exc:
        await auto_svc.update_automation(
            db_pool, slug_b, out.id, AutomationUpdate(workspace_slugs=[])
        )
    assert exc.value.status_code == 422


async def test_reorder_per_workspace_independent(db_pool: asyncpg.Pool) -> None:
    from fastapi import HTTPException

    from docflow.automations import service as auto_svc
    from docflow.schemas.automations import AutomationCreate

    _wk_a, slug_a, _ = await _mk_ws_doc(db_pool)
    _wk_b, slug_b, _ = await _mk_ws_doc(db_pool)

    ids = []
    for name in ("Alpha", "Beta"):
        out = await auto_svc.create_automation(
            db_pool,
            slug_a,
            AutomationCreate(
                label=name, event_codes=[_UPDATED],
                workspace_slugs=[slug_a, slug_b],
                url="https://x/api", http_method="POST",
            ),
        )
        ids.append(out.id)

    # Ordre initial identique (création) dans les deux workspaces.
    order_a = [a.id for a in await auto_svc.list_automations(db_pool, slug_a)]
    assert order_a == ids

    # Inverser DANS A seulement.
    await auto_svc.reorder_automations(db_pool, slug_a, [ids[1], ids[0]])
    assert [a.id for a in await auto_svc.list_automations(db_pool, slug_a)] == [ids[1], ids[0]]
    # B garde SON ordre (indépendance par workspace).
    assert [a.id for a in await auto_svc.list_automations(db_pool, slug_b)] == ids

    # Positions exposées dans le contexte du workspace demandé.
    a_list = await auto_svc.list_automations(db_pool, slug_a)
    assert [a.position for a in a_list] == [1, 2]

    # Couverture inexacte → 422.
    with pytest.raises(HTTPException) as exc:
        await auto_svc.reorder_automations(db_pool, slug_a, [ids[0]])
    assert exc.value.status_code == 422


async def test_clone_automation(db_pool: asyncpg.Pool) -> None:
    from docflow.automations import service as auto_svc
    from docflow.schemas.automations import AutomationCreate, AutomationHeaderIn

    wk, slug, doc_id = await _mk_ws_doc(db_pool)
    src = await auto_svc.create_automation(
        db_pool,
        slug,
        AutomationCreate(
            label="Rag", event_codes=[_UPDATED], block_slugs=["b"],
            url="https://rag.example/index", http_method="POST",
            body_template='{"doc": "{content}"}',
            headers=[AutomationHeaderIn(name="Authorization", value_prefix="Bearer ",
                                        secret_ref=f"${{secret://{uuid.uuid4()}}}")],
        ),
    )
    # Curseur avancé sur la source ; un event antérieur ne doit PAS être rejoué par le clone.
    await db_pool.execute(
        "INSERT INTO document_event "
        "(workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1,$2,$3,$4::jsonb)",
        wk, doc_id, _UPDATED, json.dumps({"documentId": str(doc_id)}),
    )
    seq = await db_pool.fetchval("SELECT max(seq) FROM document_event")
    await db_pool.execute(
        "INSERT INTO automation_cursor (automation_ref, last_seq) VALUES ($1, $2)",
        src.id, seq,
    )

    clone = await auto_svc.clone_automation(db_pool, slug, src.id)
    assert clone.id != src.id
    assert clone.label == "Rag (copie)"
    assert clone.active is False                      # toujours créé désactivé
    assert clone.event_codes == [_UPDATED]
    assert clone.block_slugs == ["b"]
    assert clone.workspace_slugs == src.workspace_slugs
    assert len(clone.headers) == 1                    # headers copiés (réf secret incluse)
    assert clone.headers[0].value_prefix == "Bearer "

    # Curseur aligné → pas de rejeu : 0 en attente pour le clone.
    listed = await auto_svc.list_automations(db_pool, slug)
    got = next(a for a in listed if a.id == clone.id)
    assert got.pending_count == 0
    # Aucun run copié.
    assert await db_pool.fetchval(
        "SELECT count(*) FROM automation_run WHERE automation_ref = $1", clone.id
    ) == 0


async def test_stop_chain_blocks_lower_priority(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from docflow.automations import service as auto_svc
    from docflow.schemas.automations import AutomationCreate

    _CALLS.clear()
    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeClient)

    async def _noop(url: str) -> None:
        return None

    monkeypatch.setattr(worker, "validate_public_url", _noop)

    wk, slug, doc_id = await _mk_ws_doc(db_pool)
    # A (priorité 1, stop_chain) et B (priorité 2) sur le même event.
    a = await auto_svc.create_automation(
        db_pool, slug,
        AutomationCreate(label="A", event_codes=[_UPDATED], stop_chain=True,
                         url="https://a.example/hook", http_method="POST"),
    )
    b = await auto_svc.create_automation(
        db_pool, slug,
        AutomationCreate(label="B", event_codes=[_UPDATED],
                         url="https://b.example/hook", http_method="POST"),
    )
    await db_pool.execute("UPDATE automation SET active = true WHERE id = ANY($1)", [a.id, b.id])
    await db_pool.execute(
        "INSERT INTO document_event "
        "(workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1,$2,$3,$4::jsonb)",
        wk, doc_id, _UPDATED, json.dumps({"documentId": str(doc_id)}),
    )

    await worker.tick(db_pool, object())

    # A (stop_chain, appel OK) consomme l'event → B ne le traite PAS.
    urls = [c["url"] for c in _CALLS]
    assert "https://a.example/hook" in urls
    assert "https://b.example/hook" not in urls
    # B est « à jour » : l'event consommé n'apparaît plus dans son pending.
    listed = await auto_svc.list_automations(db_pool, slug)
    assert next(x for x in listed if x.id == b.id).pending_count == 0
    # A garde la main : consumed_by = A.
    consumed = await db_pool.fetchval(
        "SELECT consumed_by FROM document_event WHERE workspace_technical_key = $1 "
        "ORDER BY seq DESC LIMIT 1", wk,
    )
    assert consumed == a.id

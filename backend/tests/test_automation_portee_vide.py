"""Portée de workspace vide = AUCUN filtre de portée, worker compris.

`test_automation_global.py` fixe déjà le contrat côté CRUD : « une portée vide
n'est PAS une saisie incomplète : c'est "aucun filtre de portée", donc l'instance
entière ». `events_query._FROM_WHERE` l'applique (`cardinality($1) = 0 OR …`), et
c'est ce que l'écran affiche : « aucun coché = tous les workspaces ».

Le worker, lui, court-circuitait sur `if not wks: return []` — l'ancienne
sémantique « aucun workspace = ne se déclenche jamais ». Conséquence observée en
production : un automate sans portée affiche un compteur d'events en attente qui
monte indéfiniment (le compteur, lui, applique la bonne règle) pendant que rien
n'est jamais traité. Aucune erreur, aucun report, aucun log : les deux côtés sont
en bonne santé, ils ne sont simplement pas d'accord.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import pytest

from docflow.automations import service, worker

_UPDATED = "docflow.document.updated.v1"


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
        _CALLS.append({"method": method, "url": url})
        return _FakeResp()


_CALLS: list[dict[str, Any]] = []


async def _ws_doc_event(pool: asyncpg.Pool) -> uuid.UUID:
    """Un workspace, un document, un event `updated` — et RIEN dans automation_workspace."""
    slug = f"portee-{uuid.uuid4().hex[:8]}"
    wk = await pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1,$2) RETURNING workspace_technical_key",
        slug,
        "Portée vide",
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
        "Doc",
    )
    await pool.execute(
        "INSERT INTO document_version (document_ref, version_number, title, content) "
        "VALUES ($1, 1, $2, $3)",
        doc_id,
        "Doc",
        "Contenu",
    )
    await pool.execute(
        "INSERT INTO document_event (workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1,$2,$3,$4::jsonb)",
        wk,
        doc_id,
        _UPDATED,
        json.dumps({"documentId": str(doc_id), "workspaceSlug": slug}),
    )
    return await pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "delay_minutes, url, http_method, body_template) "
        "VALUES ($1,$2,true,$3,0,$4,$5,$6) RETURNING id",
        wk,
        "Sans portée",
        [_UPDATED],
        "https://rag.example/index",
        "POST",
        json.dumps({"doc": "{content}"}),
    )
    # Volontairement AUCUN INSERT dans automation_workspace.


_COLS = (
    "SELECT id, workspace_technical_key, event_codes, block_slugs, block_templates, "
    "functional_type_slugs, stop_chain, delay_minutes, url, http_method, body_template "
    "FROM automation WHERE id = $1"
)


class _Settings:
    public_base_url = "https://doc.example"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _CALLS.clear()
    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeClient)

    async def _noop(url: str) -> None:
        return None

    monkeypatch.setattr(worker, "validate_public_url", _noop)


async def test_un_automate_sans_portee_traite_quand_meme_ses_events(
    db_pool: asyncpg.Pool,
) -> None:
    """Portée vide = pas de filtre : l'event doit partir, pas rester en file.

    `>= 1` et non `== 1` : sans filtre de portée, l'automate ramasse légitimement
    tous les events du schéma de test, y compris ceux des autres tests de la
    session. Exiger un compte exact rendrait ce test vert isolément et rouge dans
    la suite — ce qui est arrivé, et ce que l'assertion corrigée empêche.
    """
    auto_id = await _ws_doc_event(db_pool)
    automation = await db_pool.fetchrow(_COLS, auto_id)

    await worker.run_tick(db_pool, automation, _Settings())

    assert len(_CALLS) >= 1


async def test_le_compteur_et_le_worker_ne_se_contredisent_pas(
    db_pool: asyncpg.Pool,
) -> None:
    """Le cœur du défaut : l'écran comptait ce que le worker refusait de traiter.

    Un compteur qui monte pendant que rien n'avance ne se distingue pas d'une
    panne — et ne produit aucun log, puisque les deux côtés vont « bien ».
    """
    auto_id = await _ws_doc_event(db_pool)
    automation = await db_pool.fetchrow(_COLS, auto_id)

    async with db_pool.acquire() as conn:
        avant = await service._pending_count(conn, automation)
    # `>= 1` et non `== 1` : la portée vide compte les events de TOUS les
    # workspaces du schéma de test, y compris ceux laissés par un autre test.
    # C'est précisément la sémantique qu'on vérifie — s'en plaindre serait
    # contredire le contrat qu'on teste.
    assert avant >= 1, "le compteur voit l'event : portée vide = pas de filtre"

    await worker.run_tick(db_pool, automation, _Settings())

    async with db_pool.acquire() as conn:
        apres = await service._pending_count(conn, automation)
    assert apres == 0, "après traitement, le compteur doit retomber — le curseur a avancé"

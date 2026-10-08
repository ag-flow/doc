"""Un event de CONTENANT (workspace créé, bloc créé) n'a pas de document.

Bug `0b58769c`, reproduit en production : `automation_run.document_ref` était
`not null`, hérité d'un temps où tout event d'automate portait un document. Un
event de contenant faisait donc échouer `_record_run` APRÈS que l'appel HTTP
était parti — et comme `_advance` vient après, le curseur ne bougeait jamais :
le même event était réémis toutes les 60 secondes, indéfiniment.

Les trois garde-fous contre le ré-envoi (déduplication, curseur, dead-letter)
vivent tous dans `automation_run` : la contrainte les désactivait ensemble, d'où
une boucle NON bornée là où un échec ordinaire meurt au bout de 8 tentatives.

`migrations/0050` avait déjà rendu `document_version` facultatif pour la même
raison (« tous les events ne bumpent pas la version ») ; elle ne pouvait pas
anticiper `document_ref`, les events de contenant n'existant pas encore.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import pytest

from docflow.automations import worker

_BLOCK_CREATED = "docflow.block.created.v1"


class _FakeResp:
    status_code = 201
    is_success = True
    text = '{"created": true}'


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


async def _contenant(pool: asyncpg.Pool) -> tuple[uuid.UUID, int]:
    """Un event de bloc créé — SANS document_ref — et l'automate qui l'écoute."""
    slug = f"contenant-{uuid.uuid4().hex[:8]}"
    wk = await pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1,$2) RETURNING workspace_technical_key",
        slug,
        "Contenant",
    )
    seq: int = await pool.fetchval(
        "INSERT INTO document_event (workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1, NULL, $2, $3::jsonb) RETURNING seq",
        wk,
        _BLOCK_CREATED,
        json.dumps({"workspaceSlug": slug, "blockSlug": "documentation"}),
    )
    auto_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "delay_minutes, url, http_method, body_template) "
        "VALUES ($1,$2,true,$3,0,$4,$5,$6) RETURNING id",
        wk,
        "Créer le workspace RAG",
        [_BLOCK_CREATED],
        "https://rag.example/api/v1/workspaces",
        "POST",
        json.dumps({"name": "{event.workspaceSlug}-docs"}),
    )
    return auto_id, seq


async def test_un_event_de_contenant_enregistre_son_run_et_avance_le_curseur(
    db_pool: asyncpg.Pool,
) -> None:
    """Le cœur de l'incident : l'appel partait, mais rien n'était enregistré."""
    auto_id, seq = await _contenant(db_pool)
    automation = await db_pool.fetchrow(_COLS, auto_id)

    await worker.run_tick(db_pool, automation, _Settings())

    assert len(_CALLS) == 1, "l'appel doit partir"

    run = await db_pool.fetchrow(
        "SELECT document_ref, document_version, status, http_status FROM automation_run "
        "WHERE automation_ref = $1 AND event_seq = $2",
        auto_id,
        seq,
    )
    assert run is not None, "le run doit être enregistré même sans document"
    assert run["document_ref"] is None
    assert run["document_version"] is None
    assert run["status"] == "ok"

    cursor = await db_pool.fetchval(
        "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1", auto_id
    )
    assert cursor == seq, "le curseur doit avoir avancé, sinon l'event revient à chaque tick"


async def test_le_tick_suivant_ne_reemet_pas_le_meme_event(
    db_pool: asyncpg.Pool,
) -> None:
    """La boucle non bornée observée en production : même event, chaque minute.

    Un second tick ne doit produire AUCUN nouvel appel. C'est ce qui distingue
    un échec ordinaire — qui meurt au bout de `_MAX_ATTEMPTS` — d'une boucle que
    rien n'arrête, puisque le compteur de tentatives vit lui aussi dans la table
    qui refusait la ligne.
    """
    auto_id, _seq = await _contenant(db_pool)
    automation = await db_pool.fetchrow(_COLS, auto_id)

    await worker.run_tick(db_pool, automation, _Settings())
    appels_apres_premier_tick = len(_CALLS)

    await worker.run_tick(db_pool, automation, _Settings())

    assert len(_CALLS) == appels_apres_premier_tick, "le second tick ne doit rien réémettre"

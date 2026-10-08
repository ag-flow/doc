"""La pré-condition câblée dans le worker — les deux pannes du 2026-10-08.

L'évaluateur est testé à part (`test_automation_precheck.py`). Ici on vérifie
qu'il est réellement consulté AVANT l'appel principal, et que chaque issue a la
conséquence attendue sur l'event :

- `skip`  → aucun appel principal, run enregistré en `skipped`, curseur avancé ;
- `defer` → aucun appel principal, aucun run, curseur GELÉ (l'event revient).

Sans le câblage, l'évaluateur serait du code mort : un module correct que
personne n'appelle est un module qui n'existe pas.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import pytest

from docflow.automations import worker

_BLOCK_CREATED = "docflow.block.created.v1"
_CHECK_URL = "https://rag.example/api/v1/workspaces/test-docs"
_MAIN_URL = "https://rag.example/api/v1/workspaces"


class _Resp:
    def __init__(self, status: int, text: str) -> None:
        self.status_code = status
        self.is_success = 200 <= status < 300
        self.text = text


class _FakeClient:
    """Répond selon l'URL : la pré-vérification et l'appel principal diffèrent."""

    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *a: Any) -> bool:
        return False

    async def request(
        self, method: str, url: str, headers: Any = None, content: Any = None
    ) -> _Resp:
        _CALLS.append({"method": method, "url": url})
        if url == _CHECK_URL:
            return _Resp(_CHECK_STATUS[0], _CHECK_BODY[0])
        return _Resp(201, '{"created": true}')


_CALLS: list[dict[str, Any]] = []
_CHECK_STATUS: list[int] = [404]
_CHECK_BODY: list[str] = [""]

_COLS = (
    "SELECT id, workspace_technical_key, event_codes, block_slugs, block_templates, "
    "functional_type_slugs, stop_chain, delay_minutes, url, http_method, body_template, "
    "precheck FROM automation WHERE id = $1"
)


class _Settings:
    public_base_url = "https://doc.example"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _CALLS.clear()
    _CHECK_STATUS[0] = 404
    _CHECK_BODY[0] = ""
    monkeypatch.setattr(worker.httpx, "AsyncClient", _FakeClient)

    async def _noop(url: str) -> None:
        return None

    monkeypatch.setattr(worker, "validate_public_url", _noop)


async def _automate(pool: asyncpg.Pool, precheck: dict | None) -> tuple[uuid.UUID, int]:
    slug = f"pc-{uuid.uuid4().hex[:8]}"
    wk = await pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1,$2) RETURNING workspace_technical_key",
        slug,
        "Précondition",
    )
    seq: int = await pool.fetchval(
        "INSERT INTO document_event (workspace_technical_key, document_ref, event_code, business) "
        "VALUES ($1, NULL, $2, $3::jsonb) RETURNING seq",
        wk,
        _BLOCK_CREATED,
        json.dumps({"workspaceSlug": slug}),
    )
    auto_id: uuid.UUID = await pool.fetchval(
        "INSERT INTO automation (workspace_technical_key, label, active, event_codes, "
        "delay_minutes, url, http_method, body_template, precheck) "
        "VALUES ($1,$2,true,$3,0,$4,$5,$6,$7::jsonb) RETURNING id",
        wk,
        "Créer le workspace RAG",
        [_BLOCK_CREATED],
        _MAIN_URL,
        "POST",
        json.dumps({"name": "{event.workspaceSlug}-docs"}),
        json.dumps(precheck) if precheck is not None else None,
    )
    return auto_id, seq


_CREATE_SPEC = {
    "url": _CHECK_URL,
    "method": "GET",
    "rules": [{"status": [404], "then": "proceed"}],
    "default": "skip",
}

_INDEX_SPEC = {
    "url": _CHECK_URL,
    "method": "GET",
    "rules": [{"status": [200], "then": "proceed"}],
    "default": "defer",
}


async def test_la_precondition_autorise_l_appel_quand_la_ressource_manque(
    db_pool: asyncpg.Pool,
) -> None:
    """Cas « créer » nominal : 404 → on crée."""
    auto_id, _ = await _automate(db_pool, _CREATE_SPEC)
    automation = await db_pool.fetchrow(_COLS, auto_id)
    _CHECK_STATUS[0] = 404

    await worker.run_tick(db_pool, automation, _Settings())

    urls = [c["url"] for c in _CALLS]
    assert _CHECK_URL in urls, "la pré-vérification doit avoir lieu"
    assert _MAIN_URL in urls, "puis l'appel principal"


async def test_la_precondition_evite_le_409_quand_la_ressource_existe(
    db_pool: asyncpg.Pool,
) -> None:
    """Cas « créer » : le workspace existe → AUCUN appel principal, run `skipped`."""
    auto_id, seq = await _automate(db_pool, _CREATE_SPEC)
    automation = await db_pool.fetchrow(_COLS, auto_id)
    _CHECK_STATUS[0] = 200
    _CHECK_BODY[0] = '{"slug":"test-docs"}'

    await worker.run_tick(db_pool, automation, _Settings())

    assert _MAIN_URL not in [c["url"] for c in _CALLS], "le 409 ne doit plus jamais partir"

    run = await db_pool.fetchrow(
        "SELECT status FROM automation_run WHERE automation_ref=$1 AND event_seq=$2", auto_id, seq
    )
    assert run is not None and run["status"] == "skipped"

    cursor = await db_pool.fetchval(
        "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1", auto_id
    )
    assert cursor == seq, "un skip est un traitement : le curseur avance"


async def test_la_precondition_differe_au_lieu_de_mettre_en_dead_letter(
    db_pool: asyncpg.Pool,
) -> None:
    """Cas « indexer » : le corpus manque → on diffère, on n'échoue pas.

    C'est la différence avec aujourd'hui : un 404 brûlait les 8 tentatives puis
    abandonnait le document. Différer le garde traitable.
    """
    auto_id, seq = await _automate(db_pool, _INDEX_SPEC)
    automation = await db_pool.fetchrow(_COLS, auto_id)
    _CHECK_STATUS[0] = 404

    await worker.run_tick(db_pool, automation, _Settings())

    assert _MAIN_URL not in [c["url"] for c in _CALLS]

    run = await db_pool.fetchrow(
        "SELECT status FROM automation_run WHERE automation_ref=$1 AND event_seq=$2", auto_id, seq
    )
    assert run is None, "différer n'est pas un échec : aucun run n'est enregistré"

    cursor = await db_pool.fetchval(
        "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1", auto_id
    )
    assert cursor is None, "le curseur reste gelé : l'event sera retenté"


async def test_sans_precondition_le_comportement_est_inchange(
    db_pool: asyncpg.Pool,
) -> None:
    """Non-régression : un automate sans pré-condition appelle directement.

    On n'exige pas un compte exact d'appels : sans filtre de portée, l'automate
    ramasse aussi les events des autres tests de la session. Le contrat tient en
    deux points — aucune pré-vérification, et l'appel principal a bien lieu.
    """
    auto_id, _ = await _automate(db_pool, None)
    automation = await db_pool.fetchrow(_COLS, auto_id)

    await worker.run_tick(db_pool, automation, _Settings())

    urls = [c["url"] for c in _CALLS]
    assert _CHECK_URL not in urls, "aucune pré-vérification sans spécification"
    assert _MAIN_URL in urls

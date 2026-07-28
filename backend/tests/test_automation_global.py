"""Vue globale des automates (hors workspace) — ws_slug None.

Les automates sont des objets d'instance : une règle couvre plusieurs
workspaces. La vue globale liste tout, la création exige une portée explicite,
l'ordre global se projette sur chaque workspace.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.automations import service
from docflow.schemas.automations import AutomationCreate

_UPDATED = "docflow.document.updated.v1"


async def _ws(pool: asyncpg.Pool) -> str:
    slug = f"auto-glob-{uuid.uuid4().hex[:8]}"
    await pool.execute(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2)", slug, "Auto global"
    )
    return slug


def _body(label: str, slugs: list[str]) -> AutomationCreate:
    return AutomationCreate(
        label=label,
        event_codes=[_UPDATED],
        url="https://x/api",
        http_method="POST",
        workspace_slugs=slugs,
    )


async def test_global_list_spans_workspaces(db_pool: asyncpg.Pool) -> None:
    ws1, ws2 = await _ws(db_pool), await _ws(db_pool)
    a1 = await service.create_automation(db_pool, None, _body("Un", [ws1]))
    a2 = await service.create_automation(db_pool, None, _body("Deux", [ws2]))

    ids = {a.id for a in await service.list_automations(db_pool, None)}
    assert {a1.id, a2.id} <= ids
    # La vue par workspace reste filtrée.
    ws1_ids = {a.id for a in await service.list_automations(db_pool, ws1)}
    assert a1.id in ws1_ids and a2.id not in ws1_ids


async def test_global_create_requires_scope(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await service.create_automation(db_pool, None, _body("Sans portée", []))
    assert exc.value.status_code == 422


async def test_global_get_update_delete(db_pool: asyncpg.Pool) -> None:
    ws1 = await _ws(db_pool)
    out = await service.create_automation(db_pool, None, _body("Cible", [ws1]))

    got = await service.get_automation(db_pool, None, out.id)
    assert got.workspace_slugs == [ws1]

    await service.delete_automation(db_pool, None, out.id)
    with pytest.raises(HTTPException) as exc:
        await service.get_automation(db_pool, None, out.id)
    assert exc.value.status_code == 404


async def test_global_reorder_projects_on_workspaces(db_pool: asyncpg.Pool) -> None:
    ws1 = await _ws(db_pool)
    a1 = await service.create_automation(db_pool, None, _body("A", [ws1]))
    a2 = await service.create_automation(db_pool, None, _body("B", [ws1]))

    # L'ordre global doit couvrir TOUS les automates de l'instance.
    every = [a.id for a in await service.list_automations(db_pool, None)]
    reordered = [a2.id, a1.id] + [i for i in every if i not in {a1.id, a2.id}]
    out = await service.reorder_automations(db_pool, None, reordered)
    assert [a.id for a in out[:2]] == [a2.id, a1.id]

    # Projection : dans ws1 aussi, B passe devant A.
    ws_order = [a.id for a in await service.list_automations(db_pool, ws1)]
    assert ws_order.index(a2.id) < ws_order.index(a1.id)

    # Ordre partiel → 422.
    with pytest.raises(HTTPException) as exc:
        await service.reorder_automations(db_pool, None, [a1.id])
    assert exc.value.status_code == 422

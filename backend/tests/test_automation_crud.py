"""Round-trip CRUD automate — headers (dont préfixe Bearer sans secret)."""

from __future__ import annotations

import uuid

import asyncpg

from docflow.automations import service
from docflow.schemas.automations import (
    AutomationCreate,
    AutomationHeaderIn,
    AutomationUpdate,
)

_UPDATED = "docflow.document.updated.v1"


async def _ws(pool: asyncpg.Pool) -> str:
    slug = f"auto-crud-{uuid.uuid4().hex[:8]}"
    await pool.execute(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2)", slug, "Auto CRUD"
    )
    return slug


async def test_header_with_prefix_no_secret_roundtrips(db_pool: asyncpg.Pool) -> None:
    slug = await _ws(db_pool)
    body = AutomationCreate(
        label="Rag",
        event_codes=[_UPDATED],
        url="https://rag.example/api",
        http_method="POST",
        body_template='{"doc": "{content}"}',
        headers=[AutomationHeaderIn(name="Authorization", value_prefix="Bearer ")],
    )
    out = await service.create_automation(db_pool, slug, body)
    assert len(out.headers) == 1
    h = out.headers[0]
    assert h.name == "Authorization"
    assert h.value_prefix == "Bearer "
    assert h.secret_ref is None and h.value is None
    assert out.event_codes == [_UPDATED]

    # Relecture (comme à la réouverture de la fenêtre).
    got = await service.get_automation(db_pool, slug, out.id)
    assert len(got.headers) == 1
    assert got.headers[0].value_prefix == "Bearer "


async def test_update_replaces_headers(db_pool: asyncpg.Pool) -> None:
    slug = await _ws(db_pool)
    out = await service.create_automation(
        db_pool,
        slug,
        AutomationCreate(
            label="Rag", event_codes=[_UPDATED], url="https://x/api", http_method="POST"
        ),
    )
    # Ajoute un header d'auth via update (comme la sélection d'opération).
    upd = await service.update_automation(
        db_pool,
        slug,
        out.id,
        AutomationUpdate(
            headers=[
                AutomationHeaderIn(
                    name="Authorization",
                    value_prefix="Bearer ",
                    secret_ref=f"${{secret://{uuid.uuid4()}}}",
                )
            ]
        ),
    )
    assert len(upd.headers) == 1
    assert upd.headers[0].name == "Authorization"
    assert upd.headers[0].value_prefix == "Bearer "

    got = await service.get_automation(db_pool, slug, out.id)
    assert len(got.headers) == 1


async def test_clear_runs(db_pool: asyncpg.Pool) -> None:
    slug = await _ws(db_pool)
    out = await service.create_automation(
        db_pool, slug,
        AutomationCreate(
            label="X", event_codes=[_UPDATED], url="https://x/api", http_method="POST"
        ),
    )
    for i in range(3):
        await db_pool.execute(
            "INSERT INTO automation_run (automation_ref, document_ref, change_log_seq, status) "
            "VALUES ($1, gen_random_uuid(), $2, 'ok')",
            out.id, i,
        )
    deleted = await service.clear_runs(db_pool, slug, out.id)
    assert deleted == 3
    assert await db_pool.fetchval(
        "SELECT count(*) FROM automation_run WHERE automation_ref = $1", out.id
    ) == 0

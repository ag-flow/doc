from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.db.helpers import require_workspace
from docflow.schemas.automations import (
    AutomationCreate,
    AutomationHeaderOut,
    AutomationOut,
    AutomationRunOut,
    AutomationUpdate,
)

log = structlog.get_logger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _fetch_headers(
    conn: asyncpg.Connection, automation_id: uuid.UUID
) -> list[AutomationHeaderOut]:
    rows = await conn.fetch(
        "SELECT id, name, value, secret_ref, required, enabled "
        "FROM automation_header WHERE automation_ref = $1 ORDER BY name",
        automation_id,
    )
    return [AutomationHeaderOut(**dict(r)) for r in rows]


def _row_to_out(row: asyncpg.Record, headers: list[AutomationHeaderOut]) -> AutomationOut:
    return AutomationOut(
        id=row["id"],
        workspace_technical_key=row["workspace_technical_key"],
        label=row["label"],
        active=row["active"],
        on_create=row["on_create"],
        on_update=row["on_update"],
        delay_minutes=row["delay_minutes"],
        contract_ref=row["contract_ref"],
        operation_id=row["operation_id"],
        url=row["url"],
        http_method=row["http_method"],
        body_template=row["body_template"],
        headers=headers,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _upsert_headers(
    conn: asyncpg.Connection, automation_id: uuid.UUID, headers: list[Any]
) -> None:
    await conn.execute(
        "DELETE FROM automation_header WHERE automation_ref = $1", automation_id
    )
    for h in headers:
        await conn.execute(
            "INSERT INTO automation_header "
            "(automation_ref, name, value, secret_ref, required, enabled) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            automation_id,
            h.name,
            h.value,
            h.secret_ref,
            h.required,
            h.enabled,
        )


# ── CRUD Automations ──────────────────────────────────────────────────────────


async def list_automations(pool: asyncpg.Pool, ws_slug: str) -> list[AutomationOut]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            "SELECT id, workspace_technical_key, label, active, on_create, on_update, "
            "delay_minutes, contract_ref, operation_id, url, http_method, body_template, "
            "created_at, updated_at "
            "FROM automation WHERE workspace_technical_key = $1 ORDER BY label",
            wk,
        )
        result = []
        for row in rows:
            headers = await _fetch_headers(conn, row["id"])
            result.append(_row_to_out(row, headers))
    return result


async def create_automation(
    pool: asyncpg.Pool, ws_slug: str, body: AutomationCreate
) -> AutomationOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            "INSERT INTO automation "
            "(workspace_technical_key, label, active, on_create, on_update, delay_minutes, "
            " contract_ref, operation_id, url, http_method, body_template) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) "
            "RETURNING id, workspace_technical_key, label, active, on_create, on_update, "
            "delay_minutes, contract_ref, operation_id, url, http_method, body_template, "
            "created_at, updated_at",
            wk,
            body.label,
            body.active,
            body.on_create,
            body.on_update,
            body.delay_minutes,
            body.contract_ref,
            body.operation_id,
            body.url,
            body.http_method,
            body.body_template,
        )
        assert row is not None
        await _upsert_headers(conn, row["id"], body.headers)
        headers = await _fetch_headers(conn, row["id"])
    return _row_to_out(row, headers)


async def get_automation(
    pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID
) -> AutomationOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            "SELECT id, workspace_technical_key, label, active, on_create, on_update, "
            "delay_minutes, contract_ref, operation_id, url, http_method, body_template, "
            "created_at, updated_at "
            "FROM automation WHERE id = $1 AND workspace_technical_key = $2",
            automation_id,
            wk,
        )
        if row is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")
        headers = await _fetch_headers(conn, automation_id)
    return _row_to_out(row, headers)


async def update_automation(
    pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID, body: AutomationUpdate
) -> AutomationOut:
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        return await get_automation(pool, ws_slug, automation_id)

    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        exists = await conn.fetchval(
            "SELECT id FROM automation WHERE id=$1 AND workspace_technical_key=$2",
            automation_id, wk,
        )
        if exists is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")

        headers_data = raw.pop("headers", None)

        if raw:
            sets: list[str] = []
            values: list[Any] = [automation_id]
            scalar_map: set[str] = {
                "label", "active", "on_create", "on_update", "delay_minutes",
                "contract_ref", "operation_id", "url", "http_method", "body_template",
            }
            for k, v in raw.items():
                if k in scalar_map:
                    values.append(v)
                    sets.append(f"{k} = ${len(values)}")
            sets.append("updated_at = now()")
            await conn.execute(
                f"UPDATE automation SET {', '.join(sets)} WHERE id = $1",
                *values,
            )

        if headers_data is not None:
            await _upsert_headers(conn, automation_id, headers_data)

        row = await conn.fetchrow(
            "SELECT id, workspace_technical_key, label, active, on_create, on_update, "
            "delay_minutes, contract_ref, operation_id, url, http_method, body_template, "
            "created_at, updated_at "
            "FROM automation WHERE id = $1",
            automation_id,
        )
        assert row is not None
        headers = await _fetch_headers(conn, automation_id)
    return _row_to_out(row, headers)


async def delete_automation(
    pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID
) -> None:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        result = await conn.execute(
            "DELETE FROM automation WHERE id=$1 AND workspace_technical_key=$2",
            automation_id, wk,
        )
    if result == "DELETE 0":
        raise HTTPException(404, f"Automate {automation_id} introuvable.")


# ── Runs ──────────────────────────────────────────────────────────────────────


async def list_runs(
    pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID, limit: int = 50
) -> list[AutomationRunOut]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        exists = await conn.fetchval(
            "SELECT id FROM automation WHERE id=$1 AND workspace_technical_key=$2",
            automation_id, wk,
        )
        if exists is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")
        rows = await conn.fetch(
            "SELECT id, automation_ref, document_ref, document_version, "
            "change_log_seq, status, executed_at "
            "FROM automation_run WHERE automation_ref=$1 "
            "ORDER BY executed_at DESC LIMIT $2",
            automation_id, limit,
        )
    return [AutomationRunOut(**dict(r)) for r in rows]


async def replay_run(
    pool: asyncpg.Pool,
    ws_slug: str,
    automation_id: uuid.UUID,
    run_id: uuid.UUID,
    settings: object,
) -> AutomationRunOut:
    from docflow.automations.worker import execute

    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)

        auto_row = await conn.fetchrow(
            "SELECT id, workspace_technical_key, on_create, on_update, delay_minutes, "
            "url, http_method, body_template FROM automation "
            "WHERE id=$1 AND workspace_technical_key=$2",
            automation_id, wk,
        )
        if auto_row is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")

        run_row = await conn.fetchrow(
            "SELECT id, document_ref, document_version, change_log_seq, status "
            "FROM automation_run WHERE id=$1 AND automation_ref=$2",
            run_id, automation_id,
        )
        if run_row is None:
            raise HTTPException(404, f"Run {run_id} introuvable.")

        doc = await conn.fetchrow(
            "SELECT doc_technical_key, version, title "
            "FROM document WHERE doc_technical_key=$1",
            run_row["document_ref"],
        )
        if doc is None:
            raise HTTPException(422, "Document supprimé, rejeu impossible.")

        status = await execute(conn, auto_row, doc, doc["version"], pool, settings)

        updated = await conn.fetchrow(
            "UPDATE automation_run SET status=$1, executed_at=now(), document_version=$2 "
            "WHERE id=$3 "
            "RETURNING id, automation_ref, document_ref, document_version, "
            "change_log_seq, status, executed_at",
            status, doc["version"], run_id,
        )
    assert updated is not None
    return AutomationRunOut(**dict(updated))

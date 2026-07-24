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
        "SELECT id, name, value, secret_ref, value_prefix, required, enabled "
        "FROM automation_header WHERE automation_ref = $1 ORDER BY name",
        automation_id,
    )
    return [AutomationHeaderOut(**dict(r)) for r in rows]


async def _pending_count(conn: asyncpg.Connection, row: asyncpg.Record) -> int:
    """Nombre d'events déclencheurs au-delà du curseur (pas encore évalués)."""
    codes = list(row["event_codes"] or [])
    if not codes:
        return 0
    cursor: int = (
        await conn.fetchval(
            "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1", row["id"]
        )
        or 0
    )
    count: int = await conn.fetchval(
        "SELECT count(*) FROM document_event "
        "WHERE workspace_technical_key = $1 AND seq > $2 AND event_code = ANY($3::text[])",
        row["workspace_technical_key"],
        cursor,
        codes,
    )
    return count


def _row_to_out(
    row: asyncpg.Record, headers: list[AutomationHeaderOut], pending_count: int = 0
) -> AutomationOut:
    return AutomationOut(
        id=row["id"],
        workspace_technical_key=row["workspace_technical_key"],
        label=row["label"],
        active=row["active"],
        pending_count=pending_count,
        event_codes=list(row["event_codes"] or []),
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
    await conn.execute("DELETE FROM automation_header WHERE automation_ref = $1", automation_id)
    for h in headers:
        await conn.execute(
            "INSERT INTO automation_header "
            "(automation_ref, name, value, secret_ref, value_prefix, required, enabled) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            automation_id,
            h.name,
            h.value,
            h.secret_ref,
            h.value_prefix,
            h.required,
            h.enabled,
        )


# ── CRUD Automations ──────────────────────────────────────────────────────────


async def list_automations(pool: asyncpg.Pool, ws_slug: str) -> list[AutomationOut]:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        rows = await conn.fetch(
            "SELECT id, workspace_technical_key, label, active, event_codes, on_create, on_update, "
            "delay_minutes, contract_ref, operation_id, url, http_method, body_template, "
            "created_at, updated_at "
            "FROM automation WHERE workspace_technical_key = $1 ORDER BY label",
            wk,
        )
        result = []
        for row in rows:
            headers = await _fetch_headers(conn, row["id"])
            result.append(_row_to_out(row, headers, await _pending_count(conn, row)))
    return result


async def create_automation(
    pool: asyncpg.Pool, ws_slug: str, body: AutomationCreate
) -> AutomationOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            "INSERT INTO automation "
            "(workspace_technical_key, label, active, event_codes, on_create, on_update, "
            " delay_minutes, contract_ref, operation_id, url, http_method, body_template) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) "
            "RETURNING id, workspace_technical_key, label, active, event_codes, on_create, "
            "on_update, delay_minutes, contract_ref, operation_id, url, http_method, "
            "body_template, created_at, updated_at",
            wk,
            body.label,
            body.active,
            body.event_codes,
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
            "SELECT id, workspace_technical_key, label, active, event_codes, on_create, on_update, "
            "delay_minutes, contract_ref, operation_id, url, http_method, body_template, "
            "created_at, updated_at "
            "FROM automation WHERE id = $1 AND workspace_technical_key = $2",
            automation_id,
            wk,
        )
        if row is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")
        headers = await _fetch_headers(conn, automation_id)
        pending = await _pending_count(conn, row)
    return _row_to_out(row, headers, pending)


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
            automation_id,
            wk,
        )
        if exists is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")

        # Présence de "headers" dans le body : on réécrit depuis les objets
        # pydantic (body.headers), pas depuis le dump (dicts) — _upsert_headers
        # attend des objets (h.name, …).
        headers_present = "headers" in raw
        raw.pop("headers", None)

        if raw:
            sets: list[str] = []
            values: list[Any] = [automation_id]
            scalar_map: set[str] = {
                "label",
                "active",
                "event_codes",
                "on_create",
                "on_update",
                "delay_minutes",
                "contract_ref",
                "operation_id",
                "url",
                "http_method",
                "body_template",
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

        if headers_present:
            await _upsert_headers(conn, automation_id, body.headers or [])

        row = await conn.fetchrow(
            "SELECT id, workspace_technical_key, label, active, event_codes, on_create, on_update, "
            "delay_minutes, contract_ref, operation_id, url, http_method, body_template, "
            "created_at, updated_at "
            "FROM automation WHERE id = $1",
            automation_id,
        )
        assert row is not None
        headers = await _fetch_headers(conn, automation_id)
        pending = await _pending_count(conn, row)
    return _row_to_out(row, headers, pending)


async def delete_automation(pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID) -> None:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        result = await conn.execute(
            "DELETE FROM automation WHERE id=$1 AND workspace_technical_key=$2",
            automation_id,
            wk,
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
            automation_id,
            wk,
        )
        if exists is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")
        rows = await conn.fetch(
            "SELECT id, automation_ref, document_ref, document_version, "
            "change_log_seq, status, executed_at "
            "FROM automation_run WHERE automation_ref=$1 "
            "ORDER BY executed_at DESC LIMIT $2",
            automation_id,
            limit,
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
            "SELECT id, workspace_technical_key, url, http_method, body_template "
            "FROM automation WHERE id=$1 AND workspace_technical_key=$2",
            automation_id,
            wk,
        )
        if auto_row is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")

        run_row = await conn.fetchrow(
            "SELECT id, document_ref, event_seq, status "
            "FROM automation_run WHERE id=$1 AND automation_ref=$2",
            run_id,
            automation_id,
        )
        if run_row is None:
            raise HTTPException(404, f"Run {run_id} introuvable.")

        # L'event déclencheur (journal durable). Purgé → rejeu impossible.
        ev = await conn.fetchrow(
            "SELECT event_code, document_ref, business FROM document_event WHERE seq = $1",
            run_row["event_seq"],
        )
        if ev is None:
            raise HTTPException(422, "Event source purgé, rejeu impossible.")

        event = {
            "event_code": ev["event_code"],
            "document_ref": ev["document_ref"],
            "business": ev["business"],
        }
        status = (await execute(conn, auto_row, event, pool, settings)).status

        updated = await conn.fetchrow(
            "UPDATE automation_run SET status=$1, executed_at=now() WHERE id=$2 "
            "RETURNING id, automation_ref, document_ref, document_version, "
            "change_log_seq, status, executed_at",
            status,
            run_id,
        )
    assert updated is not None
    return AutomationRunOut(**dict(updated))


async def run_next_pending(
    pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID, settings: object
) -> dict[str, object]:
    """Exécute l'automate sur le PROCHAIN event en attente, SANS avancer le
    curseur ni enregistrer de run — test/aperçu de l'event courant.

    Retourne {status, event_code?, event_seq?} :
    - status "ok"/"failed" = l'appel HTTP a été émis (résultat) ;
    - "no_pending" = aucun event au-delà du curseur ;
    - "no_events" = aucun eventCode déclencheur sélectionné.
    """
    from docflow.automations.worker import execute

    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        auto = await conn.fetchrow(
            "SELECT id, workspace_technical_key, event_codes, url, http_method, body_template "
            "FROM automation WHERE id = $1 AND workspace_technical_key = $2",
            automation_id,
            wk,
        )
        if auto is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")
        codes = list(auto["event_codes"] or [])
        if not codes:
            return {"status": "no_events"}
        cursor: int = (
            await conn.fetchval(
                "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1", automation_id
            )
            or 0
        )
        ev = await conn.fetchrow(
            "SELECT seq, document_ref, event_code, business FROM document_event "
            "WHERE workspace_technical_key = $1 AND seq > $2 AND event_code = ANY($3::text[]) "
            "ORDER BY seq ASC LIMIT 1",
            auto["workspace_technical_key"],
            cursor,
            codes,
        )
        if ev is None:
            return {"status": "no_pending"}
        event = {
            "event_code": ev["event_code"],
            "document_ref": ev["document_ref"],
            "business": ev["business"],
        }
        res = await execute(conn, auto, event, pool, settings)
    return {
        "status": res.status,
        "http_status": res.http_status,
        "body": res.body,
        "event_code": ev["event_code"],
        "event_seq": ev["seq"],
    }

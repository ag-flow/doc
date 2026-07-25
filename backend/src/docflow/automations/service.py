from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog
from fastapi import HTTPException

from docflow.automations import events_query
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


# ── Portée multi-workspaces (table automation_workspace) ─────────────────────


async def _workspace_keys(conn: asyncpg.Connection, automation_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await conn.fetch(
        "SELECT workspace_technical_key FROM automation_workspace "
        "WHERE automation_ref = $1 ORDER BY workspace_technical_key",
        automation_id,
    )
    return [r["workspace_technical_key"] for r in rows]


async def _workspace_slugs(conn: asyncpg.Connection, automation_id: uuid.UUID) -> list[str]:
    rows = await conn.fetch(
        "SELECT w.slug FROM automation_workspace aw "
        "JOIN workspace w ON w.workspace_technical_key = aw.workspace_technical_key "
        "WHERE aw.automation_ref = $1 ORDER BY w.slug",
        automation_id,
    )
    return [r["slug"] for r in rows]


async def _resolve_workspace_keys(
    conn: asyncpg.Connection, slugs: list[str]
) -> list[uuid.UUID]:
    """Résout des slugs de workspaces en clés ; 422 si l'un est inconnu."""
    keys: list[uuid.UUID] = []
    for slug in slugs:
        key = await conn.fetchval(
            "SELECT workspace_technical_key FROM workspace WHERE slug = $1", slug
        )
        if key is None:
            raise HTTPException(422, f"workspace « {slug} » introuvable")
        keys.append(key)
    return keys


async def _set_workspaces(
    conn: asyncpg.Connection, automation_id: uuid.UUID, keys: list[uuid.UUID]
) -> None:
    """Remplace la portée. `keys` non vide (invariant : jamais aucun workspace).

    Les positions des workspaces CONSERVÉS sont préservées (l'ordre par
    workspace ne bouge pas) ; un workspace ajouté place l'automate en fin de
    liste (max+1). Synchronise la colonne d'origine sur un élément de l'ensemble.
    """
    await conn.execute(
        "DELETE FROM automation_workspace "
        "WHERE automation_ref = $1 AND workspace_technical_key != ALL($2::uuid[])",
        automation_id,
        keys,
    )
    for key in keys:
        await conn.execute(
            "INSERT INTO automation_workspace (automation_ref, workspace_technical_key, position) "
            "VALUES ($1, $2, (SELECT COALESCE(max(position), 0) + 1 FROM automation_workspace "
            "                 WHERE workspace_technical_key = $2)) "
            "ON CONFLICT (automation_ref, workspace_technical_key) DO NOTHING",
            automation_id,
            key,
        )
    await conn.execute(
        "UPDATE automation SET workspace_technical_key = $1 WHERE id = $2",
        keys[0],
        automation_id,
    )


# Clause de visibilité : l'automate est accessible depuis tout workspace coché.
_VISIBLE = (
    "EXISTS (SELECT 1 FROM automation_workspace aw "
    "WHERE aw.automation_ref = a.id AND aw.workspace_technical_key = $2)"
)


async def _pending_count(conn: asyncpg.Connection, row: asyncpg.Record) -> int:
    """Nombre d'events déclencheurs matchés au-delà du curseur (filtres inclus),
    sur TOUS les workspaces couverts par l'automate."""
    codes = list(row["event_codes"] or [])
    if not codes:
        return 0
    cursor: int = (
        await conn.fetchval(
            "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1", row["id"]
        )
        or 0
    )
    return await events_query.pending_count(
        conn,
        await _workspace_keys(conn, row["id"]),
        codes,
        list(row["block_slugs"] or []),
        list(row["functional_type_slugs"] or []),
        row["id"],
        cursor,
    )


def _row_to_out(
    row: asyncpg.Record,
    headers: list[AutomationHeaderOut],
    pending_count: int = 0,
    workspace_slugs: list[str] | None = None,
    position: int = 0,
) -> AutomationOut:
    return AutomationOut(
        id=row["id"],
        workspace_technical_key=row["workspace_technical_key"],
        label=row["label"],
        active=row["active"],
        pending_count=pending_count,
        position=position,
        workspace_slugs=workspace_slugs or [],
        event_codes=list(row["event_codes"] or []),
        block_slugs=list(row["block_slugs"] or []),
        functional_type_slugs=list(row["functional_type_slugs"] or []),
        stop_chain=row["stop_chain"],
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
        # Visible dans TOUS les workspaces cochés, trié par PRIORITÉ d'évaluation
        # dans CE workspace (position de la table de liaison).
        rows = await conn.fetch(
            "SELECT a.id, a.workspace_technical_key, a.label, a.active, a.event_codes, "
            "a.block_slugs, a.functional_type_slugs, a.stop_chain, a.on_create, a.on_update, "
            "a.delay_minutes, a.contract_ref, a.operation_id, a.url, a.http_method, "
            "a.body_template, a.created_at, a.updated_at, aw.position "
            "FROM automation a "
            "JOIN automation_workspace aw ON aw.automation_ref = a.id "
            "WHERE aw.workspace_technical_key = $1 "
            "ORDER BY aw.position, a.label",
            wk,
        )
        result = []
        for row in rows:
            headers = await _fetch_headers(conn, row["id"])
            result.append(
                _row_to_out(
                    row,
                    headers,
                    await _pending_count(conn, row),
                    await _workspace_slugs(conn, row["id"]),
                    row["position"],
                )
            )
    return result


async def reorder_automations(
    pool: asyncpg.Pool, ws_slug: str, ids: list[uuid.UUID]
) -> list[AutomationOut]:
    """Applique l'ordre `ids` (drag & drop) aux automates DU workspace.

    L'ordre est propre au workspace : le même automate peut occuper une
    position différente dans chacun de ses workspaces. `ids` doit couvrir
    exactement les automates du workspace (422 sinon).
    """
    async with pool.acquire() as conn, conn.transaction():
        wk = await require_workspace(conn, ws_slug)
        current = {
            r["automation_ref"]
            for r in await conn.fetch(
                "SELECT automation_ref FROM automation_workspace "
                "WHERE workspace_technical_key = $1",
                wk,
            )
        }
        if set(ids) != current or len(ids) != len(current):
            raise HTTPException(
                422, "l'ordre doit couvrir exactement les automates du workspace"
            )
        for i, automation_id in enumerate(ids, start=1):
            await conn.execute(
                "UPDATE automation_workspace SET position = $1 "
                "WHERE automation_ref = $2 AND workspace_technical_key = $3",
                i,
                automation_id,
                wk,
            )
    return await list_automations(pool, ws_slug)


async def create_automation(
    pool: asyncpg.Pool, ws_slug: str, body: AutomationCreate
) -> AutomationOut:
    async with pool.acquire() as conn, conn.transaction():
        wk = await require_workspace(conn, ws_slug)
        # Portée : les workspaces cochés ; vide → [workspace courant]. Jamais aucun.
        keys = (
            await _resolve_workspace_keys(conn, body.workspace_slugs)
            if body.workspace_slugs
            else [wk]
        )
        row = await conn.fetchrow(
            "INSERT INTO automation "
            "(workspace_technical_key, label, active, event_codes, block_slugs, "
            " functional_type_slugs, stop_chain, on_create, on_update, "
            " delay_minutes, contract_ref, operation_id, url, http_method, body_template) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) "
            "RETURNING id, workspace_technical_key, label, active, event_codes, block_slugs, "
            "functional_type_slugs, stop_chain, on_create, on_update, delay_minutes, contract_ref, "
            "operation_id, url, http_method, body_template, created_at, updated_at",
            keys[0],
            body.label,
            body.active,
            body.event_codes,
            body.block_slugs,
            body.functional_type_slugs,
            body.stop_chain,
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
        await _set_workspaces(conn, row["id"], keys)
        await _upsert_headers(conn, row["id"], body.headers)
        headers = await _fetch_headers(conn, row["id"])
        slugs = await _workspace_slugs(conn, row["id"])
    return _row_to_out(row, headers, 0, slugs)


async def get_automation(
    pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID
) -> AutomationOut:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        row = await conn.fetchrow(
            "SELECT a.id, a.workspace_technical_key, a.label, a.active, a.event_codes, "
            "a.block_slugs, a.functional_type_slugs, a.stop_chain, a.on_create, a.on_update, "
            "a.delay_minutes, a.contract_ref, a.operation_id, a.url, a.http_method, "
            "a.body_template, a.created_at, a.updated_at "
            "FROM automation a WHERE a.id = $1 AND " + _VISIBLE,
            automation_id,
            wk,
        )
        if row is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")
        headers = await _fetch_headers(conn, automation_id)
        pending = await _pending_count(conn, row)
        slugs = await _workspace_slugs(conn, automation_id)
    return _row_to_out(row, headers, pending, slugs)


async def update_automation(
    pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID, body: AutomationUpdate
) -> AutomationOut:
    raw = body.model_dump(exclude_unset=True)
    if not raw:
        return await get_automation(pool, ws_slug, automation_id)

    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        exists = await conn.fetchval(
            "SELECT a.id FROM automation a WHERE a.id=$1 AND " + _VISIBLE,
            automation_id,
            wk,
        )
        if exists is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")

        # Portée workspaces : remplacement de l'ensemble — JAMAIS vide.
        if "workspace_slugs" in raw:
            new_slugs = raw.pop("workspace_slugs") or []
            if not new_slugs:
                raise HTTPException(
                    422, "un automate doit couvrir au moins un workspace"
                )
            await _set_workspaces(
                conn, automation_id, await _resolve_workspace_keys(conn, new_slugs)
            )

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
                "block_slugs",
                "functional_type_slugs",
                "stop_chain",
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
            "SELECT id, workspace_technical_key, label, active, event_codes, block_slugs, "
            "functional_type_slugs, stop_chain, on_create, on_update, "
            "delay_minutes, contract_ref, operation_id, url, http_method, body_template, "
            "created_at, updated_at "
            "FROM automation WHERE id = $1",
            automation_id,
        )
        assert row is not None
        headers = await _fetch_headers(conn, automation_id)
        pending = await _pending_count(conn, row)
        slugs = await _workspace_slugs(conn, automation_id)
    return _row_to_out(row, headers, pending, slugs)


async def delete_automation(pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID) -> None:
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        result = await conn.execute(
            "DELETE FROM automation a WHERE a.id=$1 AND " + _VISIBLE,
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
            "SELECT id FROM automation a WHERE a.id=$1 AND " + _VISIBLE,
            automation_id,
            wk,
        )
        if exists is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")
        rows = await conn.fetch(
            "SELECT id, automation_ref, document_ref, document_version, "
            "change_log_seq, status, executed_at, http_status, url, "
            "request_body, response_body, event_code, manual "
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
            "FROM automation a WHERE a.id=$1 AND " + _VISIBLE,
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
        res = await execute(conn, auto_row, event, pool, settings)

        updated = await conn.fetchrow(
            "UPDATE automation_run SET status=$1, executed_at=now(), http_status=$2, "
            "url=$3, request_body=$4, response_body=$5 WHERE id=$6 "
            "RETURNING id, automation_ref, document_ref, document_version, "
            "change_log_seq, status, executed_at, http_status, url, "
            "request_body, response_body, event_code, manual",
            res.status,
            res.http_status,
            auto_row["url"],
            res.request_body,
            res.body,
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
    from docflow.automations.worker import _prune_runs, execute

    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        auto = await conn.fetchrow(
            "SELECT id, workspace_technical_key, event_codes, block_slugs, stop_chain, "
            "functional_type_slugs, url, http_method, body_template "
            "FROM automation a WHERE a.id=$1 AND " + _VISIBLE,
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
        ev = await events_query.next_matching(
            conn,
            await _workspace_keys(conn, automation_id),
            codes,
            list(auto["block_slugs"] or []),
            list(auto["functional_type_slugs"] or []),
            automation_id,
            cursor,
        )
        if ev is None:
            return {"status": "no_pending"}
        event = {
            "event_code": ev["event_code"],
            "document_ref": ev["document_ref"],
            "business": ev["business"],
        }
        res = await execute(conn, auto, event, pool, settings)

        # Historise l'appel unitaire (manuel) SANS avancer le curseur : event_seq
        # NULL → aucune dédup, l'event reste traité normalement par le worker.
        version: int | None = None
        if ev["document_ref"] is not None:
            version = await conn.fetchval(
                "SELECT version FROM document WHERE doc_technical_key = $1", ev["document_ref"]
            )
        await conn.execute(
            """
            INSERT INTO automation_run
                (automation_ref, document_ref, document_version, change_log_seq, event_seq,
                 status, http_status, url, request_body, response_body, event_code, manual)
            VALUES ($1, $2, $3, $4, NULL, $5, $6, $7, $8, $9, $10, true)
            """,
            automation_id,
            ev["document_ref"],
            version,
            ev["seq"],
            res.status,
            res.http_status,
            auto["url"],
            res.request_body,
            res.body,
            ev["event_code"],
        )
        await _prune_runs(conn, automation_id)

    return {
        "status": res.status,
        "http_status": res.http_status,
        "body": res.body,
        "event_code": ev["event_code"],
        "event_seq": ev["seq"],
    }


async def advance_pending(
    pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID, settings: object
) -> dict[str, object]:
    """Exécute l'automate sur le prochain event en attente, l'historise (run
    normal, avec event_seq) ET avance le curseur (pas manuel du worker)."""
    from docflow.automations.worker import _advance, _prune_runs, execute

    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        auto = await conn.fetchrow(
            "SELECT id, workspace_technical_key, event_codes, block_slugs, stop_chain, "
            "functional_type_slugs, url, http_method, body_template "
            "FROM automation a WHERE a.id=$1 AND " + _VISIBLE,
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
        ev = await events_query.next_matching(
            conn,
            await _workspace_keys(conn, automation_id),
            codes,
            list(auto["block_slugs"] or []),
            list(auto["functional_type_slugs"] or []),
            automation_id,
            cursor,
        )
        if ev is None:
            return {"status": "no_pending"}
        event = {
            "event_code": ev["event_code"],
            "document_ref": ev["document_ref"],
            "business": ev["business"],
        }
        res = await execute(conn, auto, event, pool, settings)
        # Chaîne de responsabilité : le pas manuel applique la même règle.
        if auto["stop_chain"] and res.status == "ok":
            await events_query.consume(conn, ev["seq"], automation_id)
        version: int | None = None
        if ev["document_ref"] is not None:
            version = await conn.fetchval(
                "SELECT version FROM document WHERE doc_technical_key = $1", ev["document_ref"]
            )
        await conn.execute(
            """
            INSERT INTO automation_run
                (automation_ref, document_ref, document_version, change_log_seq, event_seq,
                 status, http_status, url, request_body, response_body, event_code, manual)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, false)
            ON CONFLICT (automation_ref, event_seq) WHERE event_seq IS NOT NULL DO NOTHING
            """,
            automation_id,
            ev["document_ref"],
            version,
            ev["seq"],
            ev["seq"],
            res.status,
            res.http_status,
            auto["url"],
            res.request_body,
            res.body,
            ev["event_code"],
        )
        await _prune_runs(conn, automation_id)
        await _advance(conn, automation_id, ev["seq"])
    return {
        "status": res.status,
        "http_status": res.http_status,
        "body": res.body,
        "event_code": ev["event_code"],
        "event_seq": ev["seq"],
        "advanced": True,
    }


async def cursor_back(
    pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID
) -> dict[str, object]:
    """Recule le curseur d'un event : l'event précédemment traité redevient
    « en attente » (courant). N'exécute aucun appel."""
    from docflow.automations.worker import _advance

    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        auto = await conn.fetchrow(
            "SELECT workspace_technical_key, event_codes, block_slugs, functional_type_slugs "
            "FROM automation a WHERE a.id=$1 AND " + _VISIBLE,
            automation_id,
            wk,
        )
        if auto is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")
        codes = list(auto["event_codes"] or [])
        if not codes:
            return {"cursor": 0}
        cursor: int = (
            await conn.fetchval(
                "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1", automation_id
            )
            or 0
        )
        new_cursor = await events_query.prev_cursor(
            conn,
            await _workspace_keys(conn, automation_id),
            codes,
            list(auto["block_slugs"] or []),
            list(auto["functional_type_slugs"] or []),
            automation_id,
            cursor,
        )
        await _advance(conn, automation_id, new_cursor)
    return {"cursor": new_cursor}


async def clone_automation(
    pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID
) -> AutomationOut:
    """Clone un automate : configuration complète (events, filtres, portée
    workspaces, appel, headers) — créé DÉSACTIVÉ, libellé suffixé « (copie) ».

    Le curseur est ALIGNÉ sur celui de la source : le clone ne rejoue pas tout
    l'historique d'events. L'historique d'exécutions n'est pas copié.
    """
    async with pool.acquire() as conn, conn.transaction():
        wk = await require_workspace(conn, ws_slug)
        src = await conn.fetchrow(
            "SELECT a.* FROM automation a WHERE a.id=$1 AND " + _VISIBLE,
            automation_id,
            wk,
        )
        if src is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")

        row = await conn.fetchrow(
            "INSERT INTO automation "
            "(workspace_technical_key, label, active, event_codes, block_slugs, "
            " functional_type_slugs, stop_chain, on_create, on_update, delay_minutes, "
            " contract_ref, "
            " operation_id, url, http_method, body_template) "
            "VALUES ($1,$2,false,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) "
            "RETURNING id, workspace_technical_key, label, active, event_codes, block_slugs, "
            "functional_type_slugs, stop_chain, on_create, on_update, delay_minutes, contract_ref, "
            "operation_id, url, http_method, body_template, created_at, updated_at",
            src["workspace_technical_key"],
            f"{src['label']} (copie)",
            src["event_codes"],
            src["block_slugs"],
            src["functional_type_slugs"],
            src["stop_chain"],
            src["on_create"],
            src["on_update"],
            src["delay_minutes"],
            src["contract_ref"],
            src["operation_id"],
            src["url"],
            src["http_method"],
            src["body_template"],
        )
        assert row is not None
        new_id: uuid.UUID = row["id"]

        # Même portée que la source (le clone se place en fin d'ordre partout).
        await _set_workspaces(conn, new_id, await _workspace_keys(conn, automation_id))

        # Headers copiés tels quels (y compris références de secrets).
        await conn.execute(
            "INSERT INTO automation_header "
            "(automation_ref, name, value, secret_ref, value_prefix, required, enabled) "
            "SELECT $1, name, value, secret_ref, value_prefix, required, enabled "
            "FROM automation_header WHERE automation_ref = $2",
            new_id,
            automation_id,
        )

        # Curseur aligné sur la source : pas de rejeu de l'historique.
        await conn.execute(
            "INSERT INTO automation_cursor (automation_ref, last_seq, updated_at) "
            "SELECT $1, last_seq, now() FROM automation_cursor WHERE automation_ref = $2 "
            "ON CONFLICT (automation_ref) DO NOTHING",
            new_id,
            automation_id,
        )

        headers = await _fetch_headers(conn, new_id)
        slugs = await _workspace_slugs(conn, new_id)
    return _row_to_out(row, headers, 0, slugs)


async def clear_runs(pool: asyncpg.Pool, ws_slug: str, automation_id: uuid.UUID) -> int:
    """Vide l'historique d'exécutions de l'automate (le curseur est conservé)."""
    async with pool.acquire() as conn:
        wk = await require_workspace(conn, ws_slug)
        exists = await conn.fetchval(
            "SELECT a.id FROM automation a WHERE a.id=$1 AND " + _VISIBLE,
            automation_id,
            wk,
        )
        if exists is None:
            raise HTTPException(404, f"Automate {automation_id} introuvable.")
        result = await conn.execute(
            "DELETE FROM automation_run WHERE automation_ref = $1", automation_id
        )
    return int(result.split()[-1])

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import httpx
import structlog

from docflow.automations.substitution import render_and_validate

log = structlog.get_logger(__name__)

_HTTP_TIMEOUT = 15.0


# ── Résolution de secret ──────────────────────────────────────────────────────


async def resolve_secret(secret_ref: str, *, pool: asyncpg.Pool, settings: object) -> str:
    """Résout ${vault://wallet:/path} via Harpocrate. Point d'injection unique."""
    from docflow.secrets.resolver import resolve
    from docflow.secrets.secret import Secret

    harpo_url: str | None = getattr(settings, "harpocrate_url", None)
    enc_key_obj = getattr(settings, "encryption_key", None)
    enc_key: str | None = enc_key_obj.reveal() if enc_key_obj is not None else None
    return await resolve(
        Secret(secret_ref),
        harpocrate_url=harpo_url,
        pool=pool,
        enc_key=enc_key,
    )


# ── Contenu courant du document ───────────────────────────────────────────────


async def _current_content(conn: asyncpg.Connection, doc_id: uuid.UUID) -> str | None:
    val: str | None = await conn.fetchval(
        "SELECT content FROM document WHERE doc_technical_key = $1", doc_id
    )
    return val


# ── Avance le curseur ─────────────────────────────────────────────────────────


async def _advance(conn: asyncpg.Connection, automation_id: uuid.UUID, seq: int) -> None:
    await conn.execute(
        """
        INSERT INTO automation_cursor (automation_ref, last_seq, updated_at)
        VALUES ($1, $2, now())
        ON CONFLICT (automation_ref)
        DO UPDATE SET last_seq = EXCLUDED.last_seq, updated_at = now()
        """,
        automation_id,
        seq,
    )


# ── Exécution d'un appel HTTP ─────────────────────────────────────────────────


async def execute(
    conn: asyncpg.Connection,
    automation: asyncpg.Record,
    doc: asyncpg.Record,
    version: int,
    pool: asyncpg.Pool,
    settings: object,
) -> str:
    content = await _current_content(conn, doc["doc_technical_key"])
    variables = {
        "id_document": str(doc["doc_technical_key"]),
        "title": doc["title"] or "",
        "content": content or "",
    }

    headers: dict[str, str] = {}
    header_rows = await conn.fetch(
        "SELECT name, value, secret_ref, enabled FROM automation_header WHERE automation_ref = $1",
        automation["id"],
    )
    for h in header_rows:
        if not h["enabled"]:
            continue
        if h["secret_ref"]:
            try:
                headers[h["name"]] = await resolve_secret(
                    h["secret_ref"], pool=pool, settings=settings
                )
            except Exception as exc:
                log.error(
                    "automation_secret_resolution_failed",
                    automation_id=str(automation["id"]),
                    header=h["name"],
                    error=str(exc),
                )
                return "failed"
        elif h["value"] is not None:
            headers[h["name"]] = h["value"]

    body: str | None = None
    if automation["body_template"]:
        body = render_and_validate(automation["body_template"], variables)
        if body is None:
            log.warning(
                "automation_body_render_failed",
                automation_id=str(automation["id"]),
                doc_id=str(doc["doc_technical_key"]),
            )
            return "failed"
        headers.setdefault("Content-Type", "application/json")

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.request(
                automation["http_method"],
                automation["url"],
                headers=headers,
                content=body.encode() if body is not None else None,
            )
        status = "ok" if resp.is_success else "failed"
        log.info(
            "automation_executed",
            automation_id=str(automation["id"]),
            doc_id=str(doc["doc_technical_key"]),
            version=version,
            http_status=resp.status_code,
            status=status,
        )
        return status
    except Exception as exc:
        log.warning(
            "automation_http_failed",
            automation_id=str(automation["id"]),
            doc_id=str(doc["doc_technical_key"]),
            error=str(exc),
        )
        return "failed"


# ── Tick par automate ─────────────────────────────────────────────────────────


async def run_tick(pool: asyncpg.Pool, automation: asyncpg.Record, settings: object) -> None:
    natures: list[str] = []
    if automation["on_create"]:
        natures.append("C")
    if automation["on_update"]:
        natures.append("U")
    if not natures:
        return

    async with pool.acquire() as conn:
        cursor: int = (
            await conn.fetchval(
                "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1",
                automation["id"],
            )
            or 0
        )

        rows = await conn.fetch(
            """
            SELECT seq, document_ref FROM document_change_log
            WHERE workspace_technical_key = $1
              AND seq > $2
              AND nature = ANY($3::text[])
            ORDER BY seq ASC
            LIMIT 100
            """,
            automation["workspace_technical_key"],
            cursor,
            natures,
        )

        for row in rows:
            doc = await conn.fetchrow(
                "SELECT doc_technical_key, version, title "
                "FROM document WHERE doc_technical_key = $1",
                row["document_ref"],
            )
            if doc is None:
                await _advance(conn, automation["id"], row["seq"])
                continue

            version: int = doc["version"]

            already_done = await conn.fetchval(
                """
                SELECT 1 FROM automation_run
                WHERE automation_ref = $1
                  AND document_ref = $2
                  AND document_version = $3
                """,
                automation["id"],
                doc["doc_technical_key"],
                version,
            )
            if already_done:
                await _advance(conn, automation["id"], row["seq"])
                continue

            if automation["delay_minutes"] > 0:
                hot = await conn.fetchval(
                    """
                    SELECT 1 FROM document_change_log
                    WHERE document_ref = $1
                      AND occurred_at > now() - ($2 || ' minutes')::interval
                    LIMIT 1
                    """,
                    doc["doc_technical_key"],
                    str(automation["delay_minutes"]),
                )
                if hot:
                    break

            status = await execute(conn, automation, doc, version, pool, settings)

            await conn.execute(
                """
                INSERT INTO automation_run
                    (automation_ref, document_ref, document_version, change_log_seq, status)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (automation_ref, document_ref, document_version) DO NOTHING
                """,
                automation["id"],
                doc["doc_technical_key"],
                version,
                row["seq"],
                status,
            )
            await _advance(conn, automation["id"], row["seq"])


# ── Boucle principale ─────────────────────────────────────────────────────────


async def tick(pool: asyncpg.Pool, settings: object) -> None:
    async with pool.acquire() as conn:
        automations = await conn.fetch(
            "SELECT id, workspace_technical_key, on_create, on_update, "
            "delay_minutes, url, http_method, body_template "
            "FROM automation WHERE active = true"
        )

    for automation in automations:
        try:
            await run_tick(pool, automation, settings)
        except Exception as exc:
            log.error(
                "automation_run_tick_error",
                automation_id=str(automation["id"]),
                error=str(exc),
            )


async def worker_loop(pool: asyncpg.Pool, settings: object) -> None:
    tick_seconds: int = getattr(settings, "automation_tick_seconds", 60)
    log.info("automation_worker_started", tick_seconds=tick_seconds)
    while True:
        try:
            await tick(pool, settings)
        except Exception as exc:
            log.error("automation_worker_tick_failed", error=str(exc))
        await asyncio.sleep(tick_seconds)

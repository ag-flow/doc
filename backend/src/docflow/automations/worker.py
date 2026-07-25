from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any

import asyncpg
import httpx
import structlog

from docflow.automations import events_query
from docflow.automations.substitution import render_and_validate
from docflow.config.base_url import effective_base_url
from docflow.net.ssrf import SSRFError, validate_public_url

log = structlog.get_logger(__name__)

_HTTP_TIMEOUT = 15.0
# Rétention du journal d'events consommé par les automates (heures).
_EVENT_RETENTION_HOURS = 168  # 7 jours
# Longueur max de l'extrait du corps de réponse remonté (test « jouer l'event »).
_BODY_EXCERPT = 500
# Nombre de runs conservés en base par automate (historique).
_RUN_HISTORY_KEEP = 20


@dataclass
class ExecResult:
    """Résultat d'un appel d'automate : statut + détails (aperçu + historique).

    `status` = 'ok'/'failed' (2xx = ok). `http_status`/`body` renseignés quand
    l'appel HTTP a bien eu lieu ; `body` = corps/message de RÉPONSE (ou raison
    de l'échec amont : secret, corps, URL). `request_body` = corps ENVOYÉ, avec
    les variables déjà résolues."""

    status: str
    http_status: int | None = None
    body: str | None = None
    request_body: str | None = None


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


# ── Variables exposées au template ────────────────────────────────────────────


class _Snapshot:
    __slots__ = ("title", "content", "ws_slug", "block_slug")

    def __init__(
        self, title: str | None, content: str | None, ws_slug: str | None, block_slug: str | None
    ) -> None:
        self.title = title
        self.content = content
        self.ws_slug = ws_slug
        self.block_slug = block_slug


async def _doc_snapshot(conn: asyncpg.Connection, doc_id: uuid.UUID) -> _Snapshot | None:
    """Snapshot courant du document (None s'il n'existe plus).

    Contenu = document_version à la version courante ; ws_slug/block_slug servent
    à construire l'URL de consultation.
    """
    row = await conn.fetchrow(
        """
        SELECT d.title, dv.content, w.slug AS ws_slug, b.slug AS block_slug
        FROM document d
        JOIN workspace w ON w.workspace_technical_key = d.workspace_technical_key
        LEFT JOIN data_block b ON b.id = d.data_block_ref
        LEFT JOIN document_version dv
            ON dv.document_ref = d.doc_technical_key AND dv.version_number = d.version
        WHERE d.doc_technical_key = $1
        """,
        doc_id,
    )
    if row is None:
        return None
    return _Snapshot(row["title"], row["content"], row["ws_slug"], row["block_slug"])


def _doc_url(
    base_url: str | None,
    doc_id: uuid.UUID | None,
    ws_slug: str | None,
    block_slug: str | None,
) -> str:
    """URL de consultation du document dans docflow.

    Absolue si public_base_url est configuré, sinon chemin relatif. Vide si les
    éléments manquent (ex. document supprimé)."""
    if not (doc_id and ws_slug and block_slug):
        return ""
    path = f"/ws/{ws_slug}/blocs/{block_slug}/documents/{doc_id}"
    return f"{base_url.rstrip('/')}{path}" if base_url else path


def _parse_business(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _variables(
    event_code: str,
    business: dict[str, Any],
    doc_id: uuid.UUID | None,
    snap: _Snapshot | None,
    base_url: str | None,
) -> dict[str, str]:
    """Variables du body_template : contenu doc + URL + propriétés de l'event.

    - `{id_document}`, `{title}`, `{content}` : snapshot courant du document.
    - `{doc_url}` : URL de consultation du document dans docflow.
    - `{event.code}` : l'eventCode déclencheur.
    - `{event.<prop>}` : chaque propriété métier de l'event (documentId,
      workspaceSlug, blockSlug, parentId, version, functionalTypeSlug…).
    """
    doc_ref = str(doc_id) if doc_id else str(business.get("documentId", ""))
    variables: dict[str, str] = {
        "id_document": doc_ref,
        "title": snap.title or "" if snap else "",
        "content": snap.content or "" if snap else "",
        "doc_url": _doc_url(
            base_url,
            doc_id,
            snap.ws_slug if snap else None,
            snap.block_slug if snap else None,
        ),
        "event.code": event_code,
    }
    for key, value in business.items():
        variables[f"event.{key}"] = "" if value is None else str(value)
    return variables


# ── Curseur ───────────────────────────────────────────────────────────────────


async def _prune_runs(conn: asyncpg.Connection, automation_id: uuid.UUID) -> None:
    """Ne conserve que les N runs les plus récents de l'automate."""
    await conn.execute(
        """
        DELETE FROM automation_run
        WHERE automation_ref = $1 AND id NOT IN (
            SELECT id FROM automation_run WHERE automation_ref = $1
            ORDER BY executed_at DESC, id DESC LIMIT $2
        )
        """,
        automation_id,
        _RUN_HISTORY_KEEP,
    )


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
    event: dict[str, Any],
    pool: asyncpg.Pool,
    settings: object,
) -> ExecResult:
    """Exécute l'appel HTTP de l'automate pour un event donné.

    `event` = {event_code, document_ref (uuid|None), business (dict|json str)}.
    """
    business = _parse_business(event["business"])
    doc_id: uuid.UUID | None = event["document_ref"]
    snap = await _doc_snapshot(conn, doc_id) if doc_id is not None else None
    base_url = effective_base_url(settings)
    variables = _variables(event["event_code"], business, doc_id, snap, base_url)

    headers: dict[str, str] = {}
    header_rows = await conn.fetch(
        "SELECT name, value, secret_ref, value_prefix, enabled "
        "FROM automation_header WHERE automation_ref = $1",
        automation["id"],
    )
    for h in header_rows:
        if not h["enabled"]:
            continue
        prefix = h["value_prefix"] or ""
        if h["secret_ref"]:
            try:
                resolved = await resolve_secret(h["secret_ref"], pool=pool, settings=settings)
            except Exception as exc:
                log.error(
                    "automation_secret_resolution_failed",
                    automation_id=str(automation["id"]),
                    header=h["name"],
                    error=str(exc),
                )
                return ExecResult("failed", body=f"résolution du secret « {h['name']} » échouée")
            headers[h["name"]] = prefix + resolved
        elif h["value"] is not None:
            headers[h["name"]] = prefix + h["value"]

    body: str | None = None
    if automation["body_template"]:
        body = render_and_validate(automation["body_template"], variables)
        if body is None:
            log.warning(
                "automation_body_render_failed",
                automation_id=str(automation["id"]),
                event_code=event["event_code"],
            )
            return ExecResult("failed", body="corps JSON invalide après substitution")
        headers.setdefault("Content-Type", "application/json")

    try:
        await validate_public_url(automation["url"])
    except SSRFError as exc:
        log.warning(
            "automation_url_rejected",
            automation_id=str(automation["id"]),
            error=str(exc),
        )
        return ExecResult("failed", body=f"URL refusée : {exc}", request_body=body)

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
            event_code=event["event_code"],
            doc_id=str(doc_id) if doc_id else None,
            http_status=resp.status_code,
            status=status,
        )
        return ExecResult(status, resp.status_code, resp.text[:_BODY_EXCERPT], request_body=body)
    except Exception as exc:
        log.warning(
            "automation_http_failed",
            automation_id=str(automation["id"]),
            event_code=event["event_code"],
            error=str(exc),
        )
        return ExecResult("failed", body=str(exc), request_body=body)


# ── Tick par automate ─────────────────────────────────────────────────────────


async def run_tick(pool: asyncpg.Pool, automation: asyncpg.Record, settings: object) -> None:
    codes: list[str] = list(automation["event_codes"] or [])
    if not codes:
        return

    async with pool.acquire() as conn:
        cursor: int = (
            await conn.fetchval(
                "SELECT last_seq FROM automation_cursor WHERE automation_ref = $1",
                automation["id"],
            )
            or 0
        )

        # Portée multi-workspaces : les events de TOUS les workspaces couverts.
        wks: list[uuid.UUID] = [
            r["workspace_technical_key"]
            for r in await conn.fetch(
                "SELECT workspace_technical_key FROM automation_workspace "
                "WHERE automation_ref = $1",
                automation["id"],
            )
        ]
        if not wks:
            return
        rows = await events_query.matching_batch(
            conn,
            wks,
            codes,
            list(automation["block_slugs"] or []),
            list(automation["functional_type_slugs"] or []),
            cursor,
            100,
        )

        # Le curseur = plus petit seq non traité. On l'avance tant qu'aucun
        # document « chaud » (dans sa fenêtre de debounce) n'est rencontré ;
        # dès qu'on diffère un document chaud, on gèle le curseur (deferred)
        # sans bloquer le reste du batch. La table automation_run (event_seq)
        # protège contre le double traitement des events au-delà du gel.
        deferred = False

        for row in rows:
            event_seq: int = row["seq"]

            already_done = await conn.fetchval(
                "SELECT 1 FROM automation_run WHERE automation_ref = $1 AND event_seq = $2",
                automation["id"],
                event_seq,
            )
            if already_done:
                if not deferred:
                    await _advance(conn, automation["id"], event_seq)
                continue

            doc_ref: uuid.UUID | None = row["document_ref"]
            if automation["delay_minutes"] > 0 and doc_ref is not None:
                hot = await conn.fetchval(
                    """
                    SELECT 1 FROM document_event
                    WHERE document_ref = $1
                      AND occurred_at > now() - ($2 || ' minutes')::interval
                    LIMIT 1
                    """,
                    doc_ref,
                    str(automation["delay_minutes"]),
                )
                if hot:
                    deferred = True
                    continue

            event = {
                "event_code": row["event_code"],
                "document_ref": doc_ref,
                "business": row["business"],
            }
            res = await execute(conn, automation, event, pool, settings)

            version: int | None = None
            if doc_ref is not None:
                version = await conn.fetchval(
                    "SELECT version FROM document WHERE doc_technical_key = $1", doc_ref
                )

            await conn.execute(
                """
                INSERT INTO automation_run
                    (automation_ref, document_ref, document_version, change_log_seq,
                     event_seq, status, http_status, url, request_body, response_body, event_code)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (automation_ref, event_seq) WHERE event_seq IS NOT NULL DO NOTHING
                """,
                automation["id"],
                doc_ref,
                version,
                event_seq,
                event_seq,
                res.status,
                res.http_status,
                automation["url"],
                res.request_body,
                res.body,
                row["event_code"],
            )
            await _prune_runs(conn, automation["id"])
            if not deferred:
                await _advance(conn, automation["id"], event_seq)


# ── Purge du journal d'events ─────────────────────────────────────────────────


async def _purge_events(pool: asyncpg.Pool) -> None:
    """Purge les events plus vieux que la rétention ET déjà dépassés par TOUS
    les curseurs d'automation (aucun automate ne les retraitera)."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM document_event
            WHERE occurred_at < now() - ($1 || ' hours')::interval
              AND seq <= COALESCE((SELECT min(last_seq) FROM automation_cursor), seq)
            """,
            str(_EVENT_RETENTION_HOURS),
        )


# ── Boucle principale ─────────────────────────────────────────────────────────


async def tick(pool: asyncpg.Pool, settings: object) -> None:
    async with pool.acquire() as conn:
        # Ordre d'évaluation : la priorité par workspace (position de la table
        # de liaison). Un automate multi-workspaces est évalué UNE fois par
        # tick (curseur unique) — sa priorité effective est la plus haute
        # (min des positions) parmi ses workspaces.
        automations = await conn.fetch(
            "SELECT id, workspace_technical_key, event_codes, block_slugs, "
            "functional_type_slugs, delay_minutes, url, http_method, body_template, "
            "(SELECT COALESCE(min(position), 2147483647) FROM automation_workspace aw "
            " WHERE aw.automation_ref = automation.id) AS prio "
            "FROM automation WHERE active = true "
            "ORDER BY prio, created_at, id"
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

    try:
        await _purge_events(pool)
    except Exception as exc:
        log.error("automation_event_purge_failed", error=str(exc))


async def worker_loop(pool: asyncpg.Pool, settings: object) -> None:
    tick_seconds: int = getattr(settings, "automation_tick_seconds", 60)
    log.info("automation_worker_started", tick_seconds=tick_seconds)
    while True:
        try:
            await tick(pool, settings)
        except Exception as exc:
            log.error("automation_worker_tick_failed", error=str(exc))
        await asyncio.sleep(tick_seconds)

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest

from docflow.events import worker as ev_worker
from docflow.events.signing import SIGNATURE_HEADER, sign_body


@pytest.fixture()
async def clean_outbox(db_pool: asyncpg.Pool) -> AsyncIterator[None]:
    await db_pool.execute("DELETE FROM event_outbox")
    yield
    await db_pool.execute("DELETE FROM event_outbox")


async def _insert(
    pool: asyncpg.Pool, *, next_attempt: str = "now()", payload: dict | None = None
) -> uuid.UUID:
    pid = uuid.uuid4()
    body = payload or {"_eventId": str(pid), "_eventCode": "docflow.document.created.v1", "n": 1}
    await pool.execute(
        "INSERT INTO event_outbox (id, event_code, payload, occurred_at, next_attempt_at) "
        f"VALUES ($1, $2, $3, now(), {next_attempt})",
        pid,
        "docflow.document.created.v1",
        json.dumps(body),
    )
    return pid


def test_sign_body_matches_hmac() -> None:
    body = b'{"a":1}'
    # Hexdigest brut (64 car.), SANS préfixe sha256= (contrat consommateur).
    expected = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    assert sign_body("topsecret", body) == expected
    assert not sign_body("topsecret", body).startswith("sha256=")
    assert len(sign_body("topsecret", body)) == 64


def test_emission_configured() -> None:
    class S:
        workflow_ingestion_url = "https://wf"
        workflow_source_id = "docflow"
        workflow_hmac_secret = "sekret"

    assert ev_worker.emission_configured(S())

    class S2:
        workflow_ingestion_url = "https://wf"
        workflow_source_id = None
        workflow_hmac_secret = "sekret"

    assert not ev_worker.emission_configured(S2())


async def test_drain_success_marks_sent_and_signs(
    db_pool: asyncpg.Pool, clean_outbox: None
) -> None:
    pid = await _insert(db_pool)
    calls: list[tuple[bytes, dict[str, str]]] = []

    async def poster(body: bytes, headers: dict[str, str]) -> int:
        calls.append((body, headers))
        return 200

    n = await ev_worker.drain_once(db_pool, secret="s3cr3t", poster=poster)
    assert n == 1
    row = await db_pool.fetchrow(
        "SELECT sent_at, attempts, last_error FROM event_outbox WHERE id=$1", pid
    )
    assert row["sent_at"] is not None
    assert row["last_error"] is None
    # La signature couvre exactement les octets postés.
    body, headers = calls[0]
    assert headers[SIGNATURE_HEADER] == sign_body("s3cr3t", body)


async def test_drain_http_error_retries_with_backoff(
    db_pool: asyncpg.Pool, clean_outbox: None
) -> None:
    pid = await _insert(db_pool)

    async def poster(body: bytes, headers: dict[str, str]) -> int:
        return 500

    await ev_worker.drain_once(db_pool, secret="s", poster=poster)
    row = await db_pool.fetchrow(
        "SELECT sent_at, attempts, last_error, next_attempt_at > now() AS future "
        "FROM event_outbox WHERE id=$1",
        pid,
    )
    assert row["sent_at"] is None
    assert row["attempts"] == 1
    assert "HTTP 500" in row["last_error"]
    assert row["future"] is True


async def test_drain_exception_retries(db_pool: asyncpg.Pool, clean_outbox: None) -> None:
    pid = await _insert(db_pool)

    async def poster(body: bytes, headers: dict[str, str]) -> int:
        raise RuntimeError("boom réseau")

    await ev_worker.drain_once(db_pool, secret="s", poster=poster)
    row = await db_pool.fetchrow(
        "SELECT sent_at, attempts, last_error FROM event_outbox WHERE id=$1", pid
    )
    assert row["sent_at"] is None
    assert row["attempts"] == 1
    assert "boom réseau" in row["last_error"]


async def test_drain_dead_letters_after_max_attempts(
    db_pool: asyncpg.Pool, clean_outbox: None
) -> None:
    # Une entrée à MAX_ATTEMPTS-1 tentatives : le prochain échec la passe en
    # dead-letter (failed_at) et elle n'est plus réclamée (fin du retry infini).
    pid = await _insert(db_pool)
    await db_pool.execute(
        "UPDATE event_outbox SET attempts = $1 WHERE id = $2",
        ev_worker.MAX_ATTEMPTS - 1,
        pid,
    )

    async def poster(body: bytes, headers: dict[str, str]) -> int:
        return 500

    await ev_worker.drain_once(db_pool, secret="s", poster=poster)
    row = await db_pool.fetchrow("SELECT failed_at, attempts FROM event_outbox WHERE id=$1", pid)
    assert row["failed_at"] is not None
    assert row["attempts"] == ev_worker.MAX_ATTEMPTS

    # Dead-letter : plus réclamé même si dû.
    n = await ev_worker.drain_once(db_pool, secret="s", poster=poster)
    assert n == 0


async def test_purge_delivered_keeps_recent_and_dead_letter(
    db_pool: asyncpg.Pool, clean_outbox: None
) -> None:
    old = await _insert(db_pool)
    recent = await _insert(db_pool)
    dead = await _insert(db_pool)
    await db_pool.execute(
        "UPDATE event_outbox SET sent_at = now() - interval '48 hours' WHERE id=$1", old
    )
    await db_pool.execute("UPDATE event_outbox SET sent_at = now() WHERE id=$1", recent)
    await db_pool.execute(
        "UPDATE event_outbox SET failed_at = now() - interval '48 hours' WHERE id=$1", dead
    )

    purged = await ev_worker.purge_delivered(db_pool, older_than_hours=24)
    assert purged == 1
    remaining = {r["id"] for r in await db_pool.fetch("SELECT id FROM event_outbox")}
    assert old not in remaining  # livré + ancien → purgé
    assert recent in remaining  # livré mais récent → conservé
    assert dead in remaining  # dead-letter → conservé pour inspection


def test_lease_covers_worst_case_of_a_claim() -> None:
    # Invariant : le bail posé par le claim couvre le traitement SÉQUENTIEL de
    # tout le lot réclamé. Sinon une réplique concurrente peut re-réclamer une
    # ligne que le worker est encore en train de livrer → double livraison.
    chunk = ev_worker._CLAIM_CHUNK
    assert ev_worker.lease_seconds(chunk) >= chunk * ev_worker._DELIVERY_BUDGET
    # Le budget par livraison borne réellement un POST : il doit couvrir le
    # timeout httpx (appliqué par opération : connect, write, read).
    assert ev_worker._DELIVERY_BUDGET >= ev_worker._HTTP_TIMEOUT
    assert 0 < chunk <= ev_worker._CLAIM_BATCH


async def test_claim_lease_covers_the_whole_batch(
    db_pool: asyncpg.Pool, clean_outbox: None
) -> None:
    # Pendant le traitement de la n-ième ligne du lot, le bail restant sur les
    # lignes non encore traitées doit couvrir leur pire cas de traitement.
    for _ in range(ev_worker._CLAIM_CHUNK):
        await _insert(db_pool)
    remaining_lease: list[float] = []

    async def poster(body: bytes, headers: dict[str, str]) -> int:
        left = await db_pool.fetchval(
            "SELECT min(extract(epoch FROM next_attempt_at - now())) FROM event_outbox "
            "WHERE sent_at IS NULL AND failed_at IS NULL"
        )
        remaining_lease.append(float(left))
        return 200

    n = await ev_worker.drain_once(db_pool, secret="s", poster=poster)
    assert n == ev_worker._CLAIM_CHUNK
    assert len(remaining_lease) == ev_worker._CLAIM_CHUNK
    for index, left in enumerate(remaining_lease):
        still_to_process = len(remaining_lease) - index
        assert left >= still_to_process * ev_worker._DELIVERY_BUDGET


async def test_drain_bounds_a_hung_delivery(
    db_pool: asyncpg.Pool, clean_outbox: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Un poster qui ne rend jamais la main est coupé au budget : le pire cas par
    # livraison est imposé, pas espéré (c'est ce qui rend le bail vérifiable).
    monkeypatch.setattr(ev_worker, "_DELIVERY_BUDGET", 0.05)
    pid = await _insert(db_pool)

    async def poster(body: bytes, headers: dict[str, str]) -> int:
        await asyncio.sleep(30)
        return 200

    n = await asyncio.wait_for(
        ev_worker.drain_once(db_pool, secret="s", poster=poster, limit=1), timeout=5
    )
    assert n == 1
    row = await db_pool.fetchrow("SELECT sent_at, attempts FROM event_outbox WHERE id=$1", pid)
    assert row["sent_at"] is None
    assert row["attempts"] == 1


async def test_drain_processes_more_than_one_claim_chunk(
    db_pool: asyncpg.Pool, clean_outbox: None
) -> None:
    total = ev_worker._CLAIM_CHUNK + 1
    for _ in range(total):
        await _insert(db_pool)

    async def poster(body: bytes, headers: dict[str, str]) -> int:
        return 200

    n = await ev_worker.drain_once(db_pool, secret="s", poster=poster, limit=total)
    assert n == total
    pending = await db_pool.fetchval("SELECT count(*) FROM event_outbox WHERE sent_at IS NULL")
    assert pending == 0


async def test_drain_skips_not_due(db_pool: asyncpg.Pool, clean_outbox: None) -> None:
    # next_attempt_at dans le futur → non réclamé.
    await _insert(db_pool, next_attempt="now() + interval '1 hour'")
    called = False

    async def poster(body: bytes, headers: dict[str, str]) -> int:
        nonlocal called
        called = True
        return 200

    n = await ev_worker.drain_once(db_pool, secret="s", poster=poster)
    assert n == 0
    assert called is False

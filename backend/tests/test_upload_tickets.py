"""ATDD — Upload d'artefact en deux temps (fiche acae45a0).

create_upload (ticket) → PUT (dépôt vérifié des octets) → create_artifact(upload_id)
(l'artefact naît complet). Couvre les critères d'acceptation : empreinte
vérifiée au PUT, usage unique, expiration + nettoyage, extension refusée dès le
PUT, aucun artefact de 0 octet, liaison workspace + utilisateur.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import asyncpg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from docflow.app import app
from docflow.artifacts import uploads

_PNG = b"\x89PNG\r\n\x1a\n" + b"upload-ticket-payload"
_TTL = 3600
_MAX = 10 * 1024 * 1024


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _make_user(pool: asyncpg.Pool, email: str) -> uuid.UUID:
    uid: uuid.UUID = await pool.fetchval(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, true) "
        "ON CONFLICT (email) DO UPDATE SET label = EXCLUDED.label RETURNING id",
        email,
        email,
    )
    return uid


async def _ticket_row(pool: asyncpg.Pool, upload_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM upload_ticket WHERE upload_id_hash = $1",
        hashlib.sha256(upload_id.encode()).hexdigest(),
    )


# ── Parcours nominal ──────────────────────────────────────────────────────────


async def test_two_step_upload_happy_path(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    uid = await _make_user(db_pool, "up-happy@test.local")
    try:
        ticket = await uploads.create_upload(
            db_pool,
            "test-ws",
            filename="rapport.png",
            size_bytes=len(_PNG),
            sha256=_sha(_PNG),
            requested_by=uid,
            ttl_seconds=_TTL,
            max_bytes=_MAX,
        )
        upload_id = str(ticket["upload_id"])
        # À ce stade : un ticket, aucun artefact, aucun octet.
        row = await _ticket_row(db_pool, upload_id)
        assert row is not None and row["data"] is None and row["consumed_at"] is None

        stored = await uploads.store_upload(db_pool, upload_id, _PNG, max_bytes=_MAX)
        assert stored["sha256"] == _sha(_PNG)

        created = await uploads.consume_upload(
            db_pool, "test-ws", upload_id, requested_by=uid, created_by=uid, max_bytes=_MAX
        )
        assert created.deduplicated is False
        assert created.sha256 == _sha(_PNG)
        assert created.size_bytes == len(_PNG)

        # L'artefact existe ; le ticket est consommé et son blob libéré.
        art = await db_pool.fetchrow(
            "SELECT sha256, size_bytes FROM artifact WHERE id = $1", created.id
        )
        assert art is not None and art["size_bytes"] == len(_PNG)
        row = await _ticket_row(db_pool, upload_id)
        assert row is not None and row["consumed_at"] is not None and row["data"] is None
    finally:
        await db_pool.execute("DELETE FROM app_user WHERE email = 'up-happy@test.local'")


# ── Empreinte : un PUT dont le sha ne correspond pas est rejeté ────────────────


async def test_put_wrong_sha_rejected_no_artifact(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    uid = await _make_user(db_pool, "up-sha@test.local")
    tampered = bytearray(_PNG)
    tampered[-1] ^= 0xFF  # même longueur, contenu différent → sha différent
    try:
        ticket = await uploads.create_upload(
            db_pool,
            "test-ws",
            filename="x.png",
            size_bytes=len(_PNG),
            sha256=_sha(_PNG),
            requested_by=uid,
            ttl_seconds=_TTL,
            max_bytes=_MAX,
        )
        upload_id = str(ticket["upload_id"])
        with pytest.raises(HTTPException) as exc:
            await uploads.store_upload(db_pool, upload_id, bytes(tampered), max_bytes=_MAX)
        assert exc.value.status_code == 422

        # Aucun octet rangé → create_artifact échoue, aucun artefact créé.
        row = await _ticket_row(db_pool, upload_id)
        assert row is not None and row["data"] is None
        with pytest.raises(HTTPException):
            await uploads.consume_upload(
                db_pool, "test-ws", upload_id, requested_by=uid, created_by=uid, max_bytes=_MAX
            )
        assert await db_pool.fetchval("SELECT count(*) FROM artifact") == 0
    finally:
        await db_pool.execute("DELETE FROM app_user WHERE email = 'up-sha@test.local'")


# ── Usage unique : un upload_id rejoué est refusé ─────────────────────────────


async def test_replayed_upload_id_refused(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    uid = await _make_user(db_pool, "up-replay@test.local")
    try:
        ticket = await uploads.create_upload(
            db_pool,
            "test-ws",
            filename="once.png",
            size_bytes=len(_PNG),
            sha256=_sha(_PNG),
            requested_by=uid,
            ttl_seconds=_TTL,
            max_bytes=_MAX,
        )
        upload_id = str(ticket["upload_id"])
        await uploads.store_upload(db_pool, upload_id, _PNG, max_bytes=_MAX)
        await uploads.consume_upload(
            db_pool, "test-ws", upload_id, requested_by=uid, created_by=uid, max_bytes=_MAX
        )
        with pytest.raises(HTTPException) as exc:
            await uploads.consume_upload(
                db_pool, "test-ws", upload_id, requested_by=uid, created_by=uid, max_bytes=_MAX
            )
        assert exc.value.status_code == 409
    finally:
        await db_pool.execute("DELETE FROM app_user WHERE email = 'up-replay@test.local'")


# ── Expiration : refusé, et son blob nettoyé ──────────────────────────────────


async def test_expired_upload_refused_and_purged(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    uid = await _make_user(db_pool, "up-exp@test.local")
    try:
        ticket = await uploads.create_upload(
            db_pool,
            "test-ws",
            filename="stale.png",
            size_bytes=len(_PNG),
            sha256=_sha(_PNG),
            requested_by=uid,
            ttl_seconds=_TTL,
            max_bytes=_MAX,
        )
        upload_id = str(ticket["upload_id"])
        await uploads.store_upload(db_pool, upload_id, _PNG, max_bytes=_MAX)
        # Force l'expiration dans le passé.
        await db_pool.execute(
            "UPDATE upload_ticket SET expires_at = now() - interval '1 minute' "
            "WHERE upload_id_hash = $1",
            hashlib.sha256(upload_id.encode()).hexdigest(),
        )
        with pytest.raises(HTTPException) as exc:
            await uploads.consume_upload(
                db_pool, "test-ws", upload_id, requested_by=uid, created_by=uid, max_bytes=_MAX
            )
        assert exc.value.status_code == 404

        purged = await uploads.purge_expired(db_pool)
        assert purged >= 1
        assert await _ticket_row(db_pool, upload_id) is None
    finally:
        await db_pool.execute("DELETE FROM app_user WHERE email = 'up-exp@test.local'")


# ── Extension : refusée dès le PUT (registre modifié entre-temps) ─────────────


async def test_extension_removed_from_registry_rejected_at_put(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    uid = await _make_user(db_pool, "up-ext@test.local")
    # Type temporaire : évite de toucher aux extensions seedées partagées.
    await db_pool.execute(
        "INSERT INTO artifact_media_type (extension, media_type, label) "
        "VALUES ('tstx', 'application/octet-stream', 'Temp') ON CONFLICT DO NOTHING"
    )
    try:
        ticket = await uploads.create_upload(
            db_pool,
            "test-ws",
            filename="file.tstx",
            size_bytes=len(_PNG),
            sha256=_sha(_PNG),
            requested_by=uid,
            ttl_seconds=_TTL,
            max_bytes=_MAX,
        )
        upload_id = str(ticket["upload_id"])
        # L'admin retire le type du registre APRÈS l'émission du ticket.
        await db_pool.execute("DELETE FROM artifact_media_type WHERE extension = 'tstx'")
        with pytest.raises(HTTPException) as exc:
            await uploads.store_upload(db_pool, upload_id, _PNG, max_bytes=_MAX)
        assert exc.value.status_code == 422
    finally:
        await db_pool.execute("DELETE FROM artifact_media_type WHERE extension = 'tstx'")
        await db_pool.execute("DELETE FROM app_user WHERE email = 'up-ext@test.local'")


async def test_create_upload_rejects_unknown_extension(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    with pytest.raises(HTTPException) as exc:
        await uploads.create_upload(
            db_pool,
            "test-ws",
            filename="file.zzznope",
            size_bytes=10,
            sha256=_sha(b"0123456789"),
            requested_by=None,
            ttl_seconds=_TTL,
            max_bytes=_MAX,
        )
    assert exc.value.status_code == 422


# ── Aucun artefact de 0 octet à aucun moment ──────────────────────────────────


async def test_create_upload_rejects_zero_size(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    with pytest.raises(HTTPException) as exc:
        await uploads.create_upload(
            db_pool,
            "test-ws",
            filename="empty.png",
            size_bytes=0,
            sha256=_sha(b""),
            requested_by=None,
            ttl_seconds=_TTL,
            max_bytes=_MAX,
        )
    assert exc.value.status_code == 422


async def test_put_empty_body_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    ticket = await uploads.create_upload(
        db_pool,
        "test-ws",
        filename="x.png",
        size_bytes=len(_PNG),
        sha256=_sha(_PNG),
        requested_by=None,
        ttl_seconds=_TTL,
        max_bytes=_MAX,
    )
    with pytest.raises(HTTPException) as exc:
        await uploads.store_upload(db_pool, str(ticket["upload_id"]), b"", max_bytes=_MAX)
    assert exc.value.status_code == 422


async def test_put_size_mismatch_rejected(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    # Ticket annonce len(_PNG) ; on pousse un corps plus court.
    ticket = await uploads.create_upload(
        db_pool,
        "test-ws",
        filename="x.png",
        size_bytes=len(_PNG),
        sha256=_sha(_PNG),
        requested_by=None,
        ttl_seconds=_TTL,
        max_bytes=_MAX,
    )
    with pytest.raises(HTTPException) as exc:
        await uploads.store_upload(db_pool, str(ticket["upload_id"]), _PNG[:5], max_bytes=_MAX)
    assert exc.value.status_code == 422


async def test_consume_without_put_refused(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    ticket = await uploads.create_upload(
        db_pool,
        "test-ws",
        filename="x.png",
        size_bytes=len(_PNG),
        sha256=_sha(_PNG),
        requested_by=None,
        ttl_seconds=_TTL,
        max_bytes=_MAX,
    )
    with pytest.raises(HTTPException) as exc:
        await uploads.consume_upload(
            db_pool,
            "test-ws",
            str(ticket["upload_id"]),
            requested_by=None,
            created_by=None,
            max_bytes=_MAX,
        )
    assert exc.value.status_code == 409
    assert await db_pool.fetchval("SELECT count(*) FROM artifact") == 0


# ── Liaisons workspace + utilisateur ──────────────────────────────────────────


async def test_workspace_binding(db_pool: asyncpg.Pool, test_workspace: dict[str, object]) -> None:
    await db_pool.execute(
        "INSERT INTO workspace (slug, label) VALUES ('other-ws', 'Other') ON CONFLICT DO NOTHING"
    )
    try:
        ticket = await uploads.create_upload(
            db_pool,
            "test-ws",
            filename="x.png",
            size_bytes=len(_PNG),
            sha256=_sha(_PNG),
            requested_by=None,
            ttl_seconds=_TTL,
            max_bytes=_MAX,
        )
        upload_id = str(ticket["upload_id"])
        await uploads.store_upload(db_pool, upload_id, _PNG, max_bytes=_MAX)
        with pytest.raises(HTTPException) as exc:
            await uploads.consume_upload(
                db_pool, "other-ws", upload_id, requested_by=None, created_by=None, max_bytes=_MAX
            )
        assert exc.value.status_code == 404
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = 'other-ws'")


async def test_user_binding(db_pool: asyncpg.Pool, test_workspace: dict[str, object]) -> None:
    u1 = await _make_user(db_pool, "up-u1@test.local")
    u2 = await _make_user(db_pool, "up-u2@test.local")
    try:
        ticket = await uploads.create_upload(
            db_pool,
            "test-ws",
            filename="x.png",
            size_bytes=len(_PNG),
            sha256=_sha(_PNG),
            requested_by=u1,
            ttl_seconds=_TTL,
            max_bytes=_MAX,
        )
        upload_id = str(ticket["upload_id"])
        await uploads.store_upload(db_pool, upload_id, _PNG, max_bytes=_MAX)
        with pytest.raises(HTTPException) as exc:
            await uploads.consume_upload(
                db_pool, "test-ws", upload_id, requested_by=u2, created_by=u2, max_bytes=_MAX
            )
        assert exc.value.status_code == 403
    finally:
        await db_pool.execute(
            "DELETE FROM app_user WHERE email IN ('up-u1@test.local', 'up-u2@test.local')"
        )


# ── Surface MCP ───────────────────────────────────────────────────────────────


async def _mcp_session(db_pool: asyncpg.Pool, email: str) -> object:
    from docflow.mcp.session import McpSession, set_current_session
    from docflow.schemas.auth import AuthUser

    uid = await _make_user(db_pool, email)
    user = AuthUser(id=uid, email=email, label=email, is_admin=True, validated=True, disabled=False)
    return set_current_session(McpSession(user=user))


def _settings() -> object:
    from docflow.config.settings import Settings

    return Settings(
        database_url="postgresql://unused/unused",
        jwt_secret="test-upload-secret",  # type: ignore[arg-type]
        public_base_url="https://doc.example.test",
    )


async def test_mcp_two_step_via_handlers(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    from docflow.mcp import artifact_tools
    from docflow.mcp.session import reset_current_session

    token = await _mcp_session(db_pool, "up-mcp@test.local")
    try:
        settings = _settings()
        opened = json.loads(
            (
                await artifact_tools.handle_create_upload(
                    db_pool,
                    settings,  # type: ignore[arg-type]
                    {
                        "workspace_slug": "test-ws",
                        "filename": "mcp.png",
                        "size_bytes": len(_PNG),
                        "sha256": _sha(_PNG),
                    },
                )
            )[0].text
        )
        assert "upload_id" in opened
        assert opened["upload_url"] == f"https://doc.example.test/api/uploads/{opened['upload_id']}"

        # Dépôt des octets (équivalent du PUT REST).
        await uploads.store_upload(db_pool, opened["upload_id"], _PNG, max_bytes=_MAX)

        created = json.loads(
            (
                await artifact_tools.handle_create_artifact(
                    db_pool,
                    settings,  # type: ignore[arg-type]
                    {"workspace_slug": "test-ws", "upload_id": opened["upload_id"]},
                )
            )[0].text
        )
        assert created["deduplicated"] is False
        assert created["sha256"] == _sha(_PNG)
        assert created["url"].endswith(created["id"])
    finally:
        reset_current_session(token)  # type: ignore[arg-type]
        await db_pool.execute("DELETE FROM app_user WHERE email = 'up-mcp@test.local'")


async def test_mcp_create_artifact_three_way_exclusivity(
    db_pool: asyncpg.Pool, test_workspace: dict[str, object]
) -> None:
    import base64

    from docflow.mcp import artifact_tools
    from docflow.mcp.session import reset_current_session

    token = await _mcp_session(db_pool, "up-excl@test.local")
    try:
        result = json.loads(
            (
                await artifact_tools.handle_create_artifact(
                    db_pool,
                    _settings(),  # type: ignore[arg-type]
                    {
                        "workspace_slug": "test-ws",
                        "filename": "x.png",
                        "data_base64": base64.b64encode(_PNG).decode(),
                        "upload_id": "some-ticket-id-value",
                    },
                )
            )[0].text
        )
        assert "error" in result
    finally:
        reset_current_session(token)  # type: ignore[arg-type]
        await db_pool.execute("DELETE FROM app_user WHERE email = 'up-excl@test.local'")


# ── Endpoint REST PUT (streaming, plafond, ticket introuvable) ────────────────

_JWT = "test_jwt_upload_rest"


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str, max_bytes: int) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT)
    monkeypatch.setenv("ARTIFACT_MAX_BYTES", str(max_bytes))
    return TestClient(app)


def test_rest_put_caps_and_not_found(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> None:
    with _client(monkeypatch, test_schema_url, max_bytes=1024) as client:
        # Corps au-delà du plafond → 413, coupé au flux.
        big = client.put("/api/uploads/" + "a" * 40, content=b"x" * 4096)
        assert big.status_code == 413, big.text

        # upload_id bien formé mais inconnu → 404 (ticket introuvable).
        unknown = client.put("/api/uploads/" + "b" * 40, content=b"hello")
        assert unknown.status_code == 404, unknown.text

        # upload_id malformé → 404 (rejeté par le motif, aucun accès base).
        bad = client.put("/api/uploads/nope!!bad", content=b"hello")
        assert bad.status_code == 404, bad.text

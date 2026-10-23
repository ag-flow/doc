"""Table d'état éphémère `connect_flow` — garde le `ConnectState` (clé privée
éphémère + code_verifier) côté serveur entre le `start` et le `callback` du
parcours « Connecter à Harpocrate ».

Le repo ne chiffre JAMAIS lui-même : il persiste des blobs déjà chiffrés
(`*_enc`) fournis par l'appelant (Task C). Ici on vérifie seulement que le
repo les range opaques, isole par propriétaire, respecte le TTL et l'usage
unique, et que `delete_expired` purge et compte correctement.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
from cryptography.fernet import Fernet

from docflow.crypto import encrypt_str
from docflow.vault import connect_store

_FERNET_KEY = Fernet.generate_key().decode()  # clé de test générée à la volée


async def _make_user(pool: asyncpg.Pool, email: str) -> uuid.UUID:
    uid: uuid.UUID = await pool.fetchval(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, true) "
        "ON CONFLICT (email) DO UPDATE SET label = EXCLUDED.label RETURNING id",
        email,
        email,
    )
    return uid


def _enc_pair() -> tuple[str, str]:
    state_clear = '{"private_key": "very-secret-ec-key", "code_verifier": "abc123"}'
    pending_clear = (
        '{"name": "harpocrate-prod", "url": "https://vault.example", "description": "x"}'
    )
    return encrypt_str(_FERNET_KEY, state_clear), encrypt_str(_FERNET_KEY, pending_clear)


async def test_put_then_take_active_returns_row(db_pool: asyncpg.Pool) -> None:
    uid = await _make_user(db_pool, "connect-happy@test.local")
    state = "state-happy-001"
    state_enc, pending_enc = _enc_pair()
    now = datetime.now(UTC)

    await connect_store.put(
        db_pool,
        state=state,
        owner_id=uid,
        state_blob_enc=state_enc,
        pending_enc=pending_enc,
        expires_at=now + timedelta(minutes=15),
    )

    row = await connect_store.take_active(db_pool, state=state, owner_id=uid, now=now)

    assert row is not None
    assert row["state_enc"] == state_enc
    assert row["pending_enc"] == pending_enc


async def test_take_active_wrong_owner_returns_none(db_pool: asyncpg.Pool) -> None:
    owner = await _make_user(db_pool, "connect-owner@test.local")
    other = await _make_user(db_pool, "connect-other@test.local")
    state = "state-isolation-002"
    state_enc, pending_enc = _enc_pair()
    now = datetime.now(UTC)

    await connect_store.put(
        db_pool,
        state=state,
        owner_id=owner,
        state_blob_enc=state_enc,
        pending_enc=pending_enc,
        expires_at=now + timedelta(minutes=15),
    )

    row = await connect_store.take_active(db_pool, state=state, owner_id=other, now=now)

    assert row is None


async def test_take_active_after_expiry_returns_none(db_pool: asyncpg.Pool) -> None:
    uid = await _make_user(db_pool, "connect-expired@test.local")
    state = "state-expired-003"
    state_enc, pending_enc = _enc_pair()
    now = datetime.now(UTC)

    await connect_store.put(
        db_pool,
        state=state,
        owner_id=uid,
        state_blob_enc=state_enc,
        pending_enc=pending_enc,
        expires_at=now + timedelta(minutes=15),
    )

    later = now + timedelta(minutes=16)
    row = await connect_store.take_active(db_pool, state=state, owner_id=uid, now=later)

    assert row is None


async def test_take_active_after_mark_consumed_returns_none(db_pool: asyncpg.Pool) -> None:
    uid = await _make_user(db_pool, "connect-consumed@test.local")
    state = "state-consumed-004"
    state_enc, pending_enc = _enc_pair()
    now = datetime.now(UTC)

    await connect_store.put(
        db_pool,
        state=state,
        owner_id=uid,
        state_blob_enc=state_enc,
        pending_enc=pending_enc,
        expires_at=now + timedelta(minutes=15),
    )

    # take_active seul ne doit PAS consommer la ligne.
    first = await connect_store.take_active(db_pool, state=state, owner_id=uid, now=now)
    assert first is not None

    await connect_store.mark_consumed(db_pool, state=state, now=now)

    second = await connect_store.take_active(db_pool, state=state, owner_id=uid, now=now)
    assert second is None


async def test_delete_expired_removes_expired_rows_and_returns_count(
    db_pool: asyncpg.Pool,
) -> None:
    uid = await _make_user(db_pool, "connect-purge@test.local")
    now = datetime.now(UTC)
    state_enc, pending_enc = _enc_pair()

    expired_state = "state-purge-expired-005"
    live_state = "state-purge-live-006"

    await connect_store.put(
        db_pool,
        state=expired_state,
        owner_id=uid,
        state_blob_enc=state_enc,
        pending_enc=pending_enc,
        expires_at=now - timedelta(minutes=1),
    )
    await connect_store.put(
        db_pool,
        state=live_state,
        owner_id=uid,
        state_blob_enc=state_enc,
        pending_enc=pending_enc,
        expires_at=now + timedelta(minutes=15),
    )

    deleted = await connect_store.delete_expired(db_pool, now=now)

    assert deleted == 1
    # La ligne encore valide n'a pas été touchée.
    row = await connect_store.take_active(db_pool, state=live_state, owner_id=uid, now=now)
    assert row is not None
    # La ligne expirée a bien disparu (pas seulement invisible via take_active).
    remaining = await db_pool.fetchval(
        "SELECT count(*) FROM connect_flow WHERE state_hash = encode(sha256($1::bytea), 'hex')",
        expired_state.encode(),
    )
    assert remaining == 0


async def test_put_stores_blobs_opaque_never_clear(db_pool: asyncpg.Pool) -> None:
    uid = await _make_user(db_pool, "connect-opaque@test.local")
    state = "state-opaque-007"
    state_clear = "this-is-the-clear-private-key-material"
    pending_clear = "this-is-the-clear-pending-endpoint-params"
    state_enc = encrypt_str(_FERNET_KEY, state_clear)
    pending_enc = encrypt_str(_FERNET_KEY, pending_clear)
    now = datetime.now(UTC)

    await connect_store.put(
        db_pool,
        state=state,
        owner_id=uid,
        state_blob_enc=state_enc,
        pending_enc=pending_enc,
        expires_at=now + timedelta(minutes=15),
    )

    stored = await db_pool.fetchrow(
        "SELECT state_hash, state_enc, pending_enc FROM connect_flow "
        "WHERE state_hash = encode(sha256($1::bytea), 'hex')",
        state.encode(),
    )
    assert stored is not None
    # Le `state` clair n'apparaît jamais en colonne : seule son empreinte sha256.
    assert state not in stored["state_hash"]
    assert stored["state_enc"] == state_enc
    assert stored["pending_enc"] == pending_enc
    assert state_clear not in stored["state_enc"]
    assert pending_clear not in stored["pending_enc"]

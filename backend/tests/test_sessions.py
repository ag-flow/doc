"""Sessions serveur opaques et révocables (Lot A de la sortie des JWT HS256).

Repris des tests de référence a2a (`tests/test_sessions.py`), adaptés à
app_user et à l'injection explicite des TTL (conventions docflow).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from docflow.auth import session_repo
from docflow.auth.sessions import (
    hash_session_token,
    issue_session_token,
    resolve_session_user_id,
    revoke_all_sessions_for_user,
    revoke_session,
)

_IDLE = 12 * 3600
_ABS = 24 * 3600


async def _mk_user(pool: asyncpg.Pool) -> uuid.UUID:
    uid: uuid.UUID = await pool.fetchval(
        """
        INSERT INTO app_user (email, label, validated, source)
        VALUES ($1, $2, true, 'local') RETURNING id
        """,
        f"u-{uuid.uuid4().hex[:8]}@example.test",
        "U",
    )
    return uid


async def test_issue_puis_resolve_rend_l_utilisateur(db_pool: asyncpg.Pool) -> None:
    uid = await _mk_user(db_pool)
    async with db_pool.acquire() as conn:
        token = await issue_session_token(conn, uid)
        resolved = await resolve_session_user_id(
            conn, token, idle_ttl_seconds=_IDLE, absolute_ttl_seconds=_ABS
        )
    assert resolved == uid


async def test_le_jeton_clair_n_est_jamais_stocke(db_pool: asyncpg.Pool) -> None:
    """Seule l'empreinte sha256 est en base (discipline clés API / uploads)."""
    uid = await _mk_user(db_pool)
    async with db_pool.acquire() as conn:
        token = await issue_session_token(conn, uid)
    row = await db_pool.fetchrow(
        "SELECT token_hash FROM user_sessions WHERE user_id = $1", uid
    )
    assert row["token_hash"] == hash_session_token(token)
    assert row["token_hash"] != token  # jamais le clair
    # Aucune ligne ne contient la valeur brute.
    leaked = await db_pool.fetchval(
        "SELECT count(*) FROM user_sessions WHERE token_hash = $1", token
    )
    assert leaked == 0


async def test_rotation_un_nouveau_jeton_a_chaque_login(db_pool: asyncpg.Pool) -> None:
    uid = await _mk_user(db_pool)
    async with db_pool.acquire() as conn:
        t1 = await issue_session_token(conn, uid)
        t2 = await issue_session_token(conn, uid)
    assert t1 != t2
    # Les deux sessions coexistent (pas de fixation : chaque login = id neuf).
    count = await db_pool.fetchval(
        "SELECT count(*) FROM user_sessions WHERE user_id = $1 AND revoked_at IS NULL", uid
    )
    assert count == 2


async def test_jeton_inconnu_rend_none(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        assert (
            await resolve_session_user_id(
                conn, "inconnu", idle_ttl_seconds=_IDLE, absolute_ttl_seconds=_ABS
            )
            is None
        )


async def test_expiration_par_inactivite_revoque_en_base(db_pool: asyncpg.Pool) -> None:
    """Une session inactive au-delà de la fenêtre est refusée ET révoquée au
    passage (pas seulement ignorée)."""
    uid = await _mk_user(db_pool)
    async with db_pool.acquire() as conn:
        token = await issue_session_token(conn, uid)
    # last_seen_at repoussé dans le passé au-delà de l'idle TTL.
    await db_pool.execute(
        "UPDATE user_sessions SET last_seen_at = $2 WHERE user_id = $1",
        uid,
        datetime.now(UTC) - timedelta(seconds=_IDLE + 60),
    )
    async with db_pool.acquire() as conn:
        assert (
            await resolve_session_user_id(
                conn, token, idle_ttl_seconds=_IDLE, absolute_ttl_seconds=_ABS
            )
            is None
        )
    row = await db_pool.fetchrow("SELECT revoked_at FROM user_sessions WHERE user_id = $1", uid)
    assert row["revoked_at"] is not None


async def test_plafond_absolu_malgre_activite_continue(db_pool: asyncpg.Pool) -> None:
    """Session active en permanence (last_seen_at récent) mais auth_time trop
    ancien : refusée par le plafond absolu, et révoquée."""
    uid = await _mk_user(db_pool)
    async with db_pool.acquire() as conn:
        token = await issue_session_token(conn, uid)
    # auth_time dépasse le plafond absolu ; last_seen_at reste récent (activité).
    await db_pool.execute(
        "UPDATE user_sessions SET auth_time = $2, last_seen_at = now() WHERE user_id = $1",
        uid,
        datetime.now(UTC) - timedelta(seconds=_ABS + 60),
    )
    async with db_pool.acquire() as conn:
        assert (
            await resolve_session_user_id(
                conn, token, idle_ttl_seconds=_IDLE, absolute_ttl_seconds=_ABS
            )
            is None
        )
    row = await db_pool.fetchrow("SELECT revoked_at FROM user_sessions WHERE user_id = $1", uid)
    assert row["revoked_at"] is not None


async def test_resolve_fait_glisser_last_seen_sans_toucher_auth_time(
    db_pool: asyncpg.Pool,
) -> None:
    uid = await _mk_user(db_pool)
    async with db_pool.acquire() as conn:
        token = await issue_session_token(conn, uid)
    before = await db_pool.fetchrow(
        "SELECT auth_time, last_seen_at FROM user_sessions WHERE user_id = $1", uid
    )
    # Recule last_seen_at (mais dans la fenêtre) pour observer le glissement.
    await db_pool.execute(
        "UPDATE user_sessions SET last_seen_at = $2 WHERE user_id = $1",
        uid,
        datetime.now(UTC) - timedelta(seconds=60),
    )
    async with db_pool.acquire() as conn:
        await resolve_session_user_id(
            conn, token, idle_ttl_seconds=_IDLE, absolute_ttl_seconds=_ABS
        )
    after = await db_pool.fetchrow(
        "SELECT auth_time, last_seen_at FROM user_sessions WHERE user_id = $1", uid
    )
    assert after["auth_time"] == before["auth_time"]  # jamais rafraîchi
    assert after["last_seen_at"] > datetime.now(UTC) - timedelta(seconds=5)  # glissé à now


async def test_revoke_session_refuse_un_jeton_copie(db_pool: asyncpg.Pool) -> None:
    """Le cœur du ticket : après révocation (déconnexion), un jeton copié avant
    cesse immédiatement de valoir."""
    uid = await _mk_user(db_pool)
    async with db_pool.acquire() as conn:
        token = await issue_session_token(conn, uid)
        await revoke_session(conn, token)
        assert (
            await resolve_session_user_id(
                conn, token, idle_ttl_seconds=_IDLE, absolute_ttl_seconds=_ABS
            )
            is None
        )


async def test_revoke_all_coupe_toutes_les_sessions(db_pool: asyncpg.Pool) -> None:
    uid = await _mk_user(db_pool)
    async with db_pool.acquire() as conn:
        t1 = await issue_session_token(conn, uid)
        t2 = await issue_session_token(conn, uid)
        n = await revoke_all_sessions_for_user(conn, uid)
        assert n == 2
        for t in (t1, t2):
            assert (
                await resolve_session_user_id(
                    conn, t, idle_ttl_seconds=_IDLE, absolute_ttl_seconds=_ABS
                )
                is None
            )


async def test_delete_expired_purge_les_lignes_mortes(db_pool: asyncpg.Pool) -> None:
    uid = await _mk_user(db_pool)
    async with db_pool.acquire() as conn:
        await issue_session_token(conn, uid)
    # Rend la session morte (inactive au-delà du seuil de purge).
    await db_pool.execute(
        "UPDATE user_sessions SET last_seen_at = $2 WHERE user_id = $1",
        uid,
        datetime.now(UTC) - timedelta(days=30),
    )
    async with db_pool.acquire() as conn:
        deleted = await session_repo.delete_expired(
            conn, older_than=datetime.now(UTC) - timedelta(days=7)
        )
    assert deleted >= 1
    remaining = await db_pool.fetchval(
        "SELECT count(*) FROM user_sessions WHERE user_id = $1", uid
    )
    assert remaining == 0


@pytest.mark.parametrize("bad", ["", "pas-un-hash", "z" * 64])
async def test_contrainte_empreinte_hex64(db_pool: asyncpg.Pool, bad: str) -> None:
    """La colonne token_hash n'accepte qu'une empreinte sha256 hex (64 car.)."""
    uid = await _mk_user(db_pool)
    with pytest.raises(asyncpg.PostgresError):
        await db_pool.execute(
            "INSERT INTO user_sessions (user_id, token_hash) VALUES ($1, $2)", uid, bad
        )

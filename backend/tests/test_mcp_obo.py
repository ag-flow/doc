from __future__ import annotations

import json
import uuid

import asyncpg

from docflow.mcp.obo import resolve_actor_user, verify_actor
from docflow.mcp.server import _create_workspace, configure
from docflow.mcp.session import McpSession, reset_current_session, set_current_session
from docflow.schemas.auth import AuthUser

# Vecteur d'interop figé du contrat OBO.
_SECRET = "shared-key-EXAMPLE"
_ACTOR = "gael"
_TS = "1763000000"
_SIG = "6c1a34eb1b1ca3d9be66ea366460a397e5a684fa647f302368cc7237e8ec93ae"


# ── verify_actor (crypto figée) ────────────────────────────────────────────────


def test_verify_actor_interop_vector() -> None:
    # now dans la fenêtre du timestamp du vecteur.
    assert verify_actor(_ACTOR, _TS, _SIG, _SECRET, now=float(_TS)) is True


def test_verify_actor_signature_falsifiee() -> None:
    tampered = "0" * 64
    assert verify_actor(_ACTOR, _TS, tampered, _SECRET, now=float(_TS)) is False


def test_verify_actor_hors_fenetre() -> None:
    # now très éloigné du timestamp signé → rejet anti-rejeu, même signature valide.
    assert verify_actor(_ACTOR, _TS, _SIG, _SECRET, now=float(_TS) + 10_000) is False


def test_verify_actor_timestamp_non_entier() -> None:
    assert verify_actor(_ACTOR, "pas-un-entier", _SIG, _SECRET, now=float(_TS)) is False


def test_verify_actor_mauvais_secret() -> None:
    assert verify_actor(_ACTOR, _TS, _SIG, "autre-cle", now=float(_TS)) is False


# ── resolve_actor_user (rapprochement app_user par oidc_subject) ────────────────


class _Headers:
    """Mime les en-têtes Starlette : accès insensible à la casse via .get()."""

    def __init__(self, data: dict[str, str]) -> None:
        self._data = {k.lower(): v for k, v in data.items()}

    def get(self, name: str) -> str | None:
        return self._data.get(name.lower())


def _signed_headers(actor: str, timestamp: str, signature: str) -> _Headers:
    return _Headers(
        {
            "X-Portal-Actor": actor,
            "X-Portal-Actor-Timestamp": timestamp,
            "X-Portal-Actor-Signature": signature,
        }
    )


async def _insert_user(pool: asyncpg.Pool, *, subject: str, email: str) -> uuid.UUID:
    row = await pool.fetchrow(
        "INSERT INTO app_user (email, label, validated, oidc_subject) "
        "VALUES ($1, $2, true, $3) RETURNING id",
        email,
        "OBO Test",
        subject,
    )
    assert row is not None
    uid: uuid.UUID = row["id"]
    return uid


async def test_resolve_actor_user_nominal(db_pool: asyncpg.Pool) -> None:
    email = "obo-nominal@test.local"
    try:
        uid = await _insert_user(db_pool, subject=_ACTOR, email=email)
        # now par défaut = maintenant : on resigne pour un timestamp courant.
        import hashlib
        import hmac
        import time

        ts = str(int(time.time()))
        sig = hmac.new(_SECRET.encode(), f"{_ACTOR}\n{ts}".encode(), hashlib.sha256).hexdigest()
        user = await resolve_actor_user(db_pool, _signed_headers(_ACTOR, ts, sig), _SECRET)
        assert user is not None
        assert user.id == uid
        assert user.email == email
    finally:
        await db_pool.execute("DELETE FROM app_user WHERE email = $1", email)


async def test_resolve_actor_user_signature_ko(db_pool: asyncpg.Pool) -> None:
    email = "obo-sigko@test.local"
    try:
        await _insert_user(db_pool, subject=_ACTOR, email=email)
        headers = _signed_headers(_ACTOR, _TS, "0" * 64)
        assert await resolve_actor_user(db_pool, headers, _SECRET) is None
    finally:
        await db_pool.execute("DELETE FROM app_user WHERE email = $1", email)


async def test_resolve_actor_user_headers_absents(db_pool: asyncpg.Pool) -> None:
    assert await resolve_actor_user(db_pool, _Headers({}), _SECRET) is None


async def test_resolve_actor_user_sub_inconnu(db_pool: asyncpg.Pool) -> None:
    import hashlib
    import hmac
    import time

    ts = str(int(time.time()))
    sig = hmac.new(_SECRET.encode(), f"inconnu\n{ts}".encode(), hashlib.sha256).hexdigest()
    headers = _signed_headers("inconnu", ts, sig)
    assert await resolve_actor_user(db_pool, headers, _SECRET) is None


# ── Estampillage create_workspace (owner_id = utilisateur agissant) ─────────────


def _auth_user(uid: uuid.UUID, email: str) -> AuthUser:
    return AuthUser(
        id=uid,
        email=email,
        label="U",
        is_admin=False,
        validated=True,
        disabled=False,
    )


async def test_create_workspace_owner_est_lhumain_obo(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    key_email = "obo-key@test.local"
    human_email = "obo-human@test.local"
    slug = "obo-ws-human"
    try:
        key_id = await _insert_user(db_pool, subject="key-sub", email=key_email)
        human_id = await _insert_user(db_pool, subject="human-sub", email=human_email)
        session = McpSession(
            user=_auth_user(key_id, key_email),
            api_key_scopes=[],
            api_key_admin=True,
            actor_user=_auth_user(human_id, human_email),
        )
        token = set_current_session(session)
        try:
            result = json.loads(
                (await _create_workspace(db_pool, {"slug": slug, "label": "OBO WS"}))[0].text
            )
            assert result["created"] is True
            owner = await db_pool.fetchval("SELECT owner_id FROM workspace WHERE slug = $1", slug)
            assert owner == human_id
        finally:
            reset_current_session(token)
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", slug)
        await db_pool.execute(
            "DELETE FROM app_user WHERE email = ANY($1::text[])", [key_email, human_email]
        )


async def test_create_workspace_owner_est_la_cle_sans_obo(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    key_email = "obo-key-only@test.local"
    slug = "obo-ws-key"
    try:
        key_id = await _insert_user(db_pool, subject="key-only-sub", email=key_email)
        session = McpSession(
            user=_auth_user(key_id, key_email),
            api_key_scopes=[],
            api_key_admin=True,
            actor_user=None,
        )
        token = set_current_session(session)
        try:
            result = json.loads(
                (await _create_workspace(db_pool, {"slug": slug, "label": "Key WS"}))[0].text
            )
            assert result["created"] is True
            owner = await db_pool.fetchval("SELECT owner_id FROM workspace WHERE slug = $1", slug)
            assert owner == key_id
        finally:
            reset_current_session(token)
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", slug)
        await db_pool.execute("DELETE FROM app_user WHERE email = $1", key_email)

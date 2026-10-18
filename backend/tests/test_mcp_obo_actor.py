"""Ingress MCP OBO capte l'acteur (Task 2 — suite de Task 1).

`document_event.actor_guid` existe et se relit déjà (migration 0081,
`from_event_row`). Ce qui manquait : le GUID validé par `resolve_actor_user`
(en-tête `x-portal-actor`) n'était jamais lié au contexte de corrélation
ambiant, donc jamais écrit sur l'event d'une mutation déclenchée via l'ingress
MCP OBO. Ces tests exercent la même construction de session que `_mcp_sse`
(`_build_session`) puis la liaison d'acteur câblée dans le router, sans
rejouer tout le protocole SSE (hors périmètre : seul le câblage ingress est
sous test, pas le transport MCP lui-même).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import asyncpg

from docflow.mcp import router as mcp_router
from docflow.mcp.server import _create_document, configure
from docflow.mcp.session import reset_current_session, set_current_session
from docflow.observability import correlation as corr
from docflow.schemas.auth import AuthUser

# Secret HMAC = la clé API en clair présentée sur la requête (contrat OBO,
# cf. mcp/obo.py:verify_actor) — on la signe nous-mêmes ici, aucun import du
# dépôt voisin `rag`.
_API_KEY = "obo-actor-ingress-secret"


class _Headers:
    """Mime les en-têtes Starlette : `.get()` insensible à la casse."""

    def __init__(self, data: dict[str, str]) -> None:
        self._data = {k.lower(): v for k, v in data.items()}

    def get(self, name: str) -> str | None:
        return self._data.get(name.lower())


class _FakeRequest:
    """Substitut minimal de `starlette.Request` : `_build_session` et le
    câblage ingress ne lisent que `.headers` et `.state`."""

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = _Headers(headers)
        self.state = type("_State", (), {})()


def _sign(actor: str, timestamp: str) -> str:
    payload = f"{actor}\n{timestamp}".encode()
    return hmac.new(_API_KEY.encode(), payload, hashlib.sha256).hexdigest()


async def _insert_user(pool: asyncpg.Pool, *, identity: str, email: str) -> uuid.UUID:
    row = await pool.fetchrow(
        "INSERT INTO app_user (email, label, validated, identity) "
        "VALUES ($1, $2, true, $3) RETURNING id",
        email,
        "OBO Actor Ingress Test",
        identity,
    )
    assert row is not None
    uid: uuid.UUID = row["id"]
    return uid


def _auth_user(uid: uuid.UUID, email: str) -> AuthUser:
    return AuthUser(id=uid, email=email, label="U", is_admin=True, validated=True, disabled=False)


async def _make_block(pool: asyncpg.Pool, *, ws_slug: str, type_slug: str, block_slug: str) -> None:
    wk = await pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $1) RETURNING workspace_technical_key",
        ws_slug,
    )
    root_type_id = await pool.fetchval(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) "
        "VALUES ($1, $1, $2) RETURNING id",
        type_slug,
        wk,
    )
    await pool.execute(
        "INSERT INTO data_block (slug, label, functional_type_ref, workspace_technical_key) "
        "VALUES ($1, $1, $2, $3)",
        block_slug,
        root_type_id,
        wk,
    )


async def _last_event_actor_guid(pool: asyncpg.Pool, doc_id: str) -> str | None:
    value: str | None = await pool.fetchval(
        "SELECT actor_guid FROM document_event WHERE document_ref = $1 "
        "ORDER BY seq DESC LIMIT 1",
        uuid.UUID(doc_id),
    )
    return value


async def test_ingress_avec_entetes_obo_valides_porte_lacteur_sur_levent(
    db_pool: asyncpg.Pool,
) -> None:
    configure(db_pool)
    ws_slug = "obo-actor-ingress-ws"
    type_slug = "obo-actor-ingress-type"
    block_slug = "obo-actor-ingress-block"
    key_email = "obo-actor-ingress-key@test.local"
    human_email = "obo-actor-ingress-human@test.local"
    actor_guid = "obo-actor-ingress-guid-1"
    try:
        key_id = await _insert_user(db_pool, identity="ingress-key-sub", email=key_email)
        await _insert_user(db_pool, identity=actor_guid, email=human_email)
        await _make_block(db_pool, ws_slug=ws_slug, type_slug=type_slug, block_slug=block_slug)

        timestamp = str(int(time.time()))
        headers = {
            "x-portal-actor": actor_guid,
            "x-portal-actor-timestamp": timestamp,
            "x-portal-actor-signature": _sign(actor_guid, timestamp),
        }
        request = _FakeRequest(headers)
        session = await mcp_router._build_session(
            request, _auth_user(key_id, key_email), _API_KEY
        )
        # La signature est valide : l'acteur OBO doit avoir été résolu.
        assert session.actor_user is not None
        assert session.actor_user.id == (
            await db_pool.fetchval("SELECT id FROM app_user WHERE email = $1", human_email)
        )

        session_token = set_current_session(session)
        corr_token = mcp_router._bind_actor_from_request(session, request)
        assert corr_token is not None
        try:
            result = await _create_document(
                db_pool,
                {
                    "workspace_slug": ws_slug,
                    "block_slug": block_slug,
                    "title": "Doc ingress OBO",
                    "functional_type_slug": type_slug,
                },
            )
            created = json.loads(result[0].text)
            assert created["created"] is True
        finally:
            corr.reset(corr_token)
            reset_current_session(session_token)

        assert await _last_event_actor_guid(db_pool, created["id"]) == actor_guid
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", ws_slug)
        await db_pool.execute(
            "DELETE FROM app_user WHERE email = ANY($1::text[])", [key_email, human_email]
        )


async def test_ingress_sans_entetes_obo_actor_guid_reste_null(db_pool: asyncpg.Pool) -> None:
    configure(db_pool)
    ws_slug = "obo-actor-ingress-ws2"
    type_slug = "obo-actor-ingress-type2"
    block_slug = "obo-actor-ingress-block2"
    key_email = "obo-actor-ingress-key2@test.local"
    try:
        key_id = await _insert_user(db_pool, identity="ingress-key-sub2", email=key_email)
        await _make_block(db_pool, ws_slug=ws_slug, type_slug=type_slug, block_slug=block_slug)

        request = _FakeRequest({})  # aucun en-tête OBO
        session = await mcp_router._build_session(
            request, _auth_user(key_id, key_email), _API_KEY
        )
        assert session.actor_user is None

        session_token = set_current_session(session)
        corr_token = mcp_router._bind_actor_from_request(session, request)
        assert corr_token is None  # rien à lier : pas d'acteur résolu
        try:
            result = await _create_document(
                db_pool,
                {
                    "workspace_slug": ws_slug,
                    "block_slug": block_slug,
                    "title": "Doc ingress sans OBO",
                    "functional_type_slug": type_slug,
                },
            )
            created = json.loads(result[0].text)
            assert created["created"] is True
        finally:
            reset_current_session(session_token)

        assert await _last_event_actor_guid(db_pool, created["id"]) is None
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = $1", ws_slug)
        await db_pool.execute("DELETE FROM app_user WHERE email = $1", key_email)

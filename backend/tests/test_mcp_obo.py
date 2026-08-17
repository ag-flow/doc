from __future__ import annotations

import json
import uuid

import asyncpg

from docflow.mcp.obo import resolve_actor_user, verify_actor
from docflow.mcp.server import _call_tool, _create_workspace, configure
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


# ── resolve_actor_user (rapprochement app_user par identity — contrat v6 GUID-only) ──


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
    # Contrat v6 : l'acteur est mappé sur app_user.identity (GUID-only).
    row = await pool.fetchrow(
        "INSERT INTO app_user (email, label, validated, identity) "
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


# ── Droits = porteur de la clé ; attribution = acteur OBO ──────────────────────
#
# Décision « attribution seule » : l'acteur OBO (forgeable par le porteur de la
# clé, cf. verify_actor dont le secret HMAC est la clé elle-même) ne doit JAMAIS
# gouverner les droits d'accès — uniquement l'estampillage de propriété.


async def _insert_ws(pool: asyncpg.Pool, slug: str, owner_id: uuid.UUID | None) -> uuid.UUID:
    wk: uuid.UUID = await pool.fetchval(
        "INSERT INTO workspace (slug, label, owner_id) VALUES ($1, $1, $2) "
        "RETURNING workspace_technical_key",
        slug,
        owner_id,
    )
    return wk


async def _cleanup(pool: asyncpg.Pool, *, slugs: list[str], emails: list[str]) -> None:
    await pool.execute("DELETE FROM workspace WHERE slug = ANY($1::text[])", slugs)
    await pool.execute("DELETE FROM app_user WHERE email = ANY($1::text[])", emails)


async def test_acces_refuse_si_porteur_sans_acces_meme_avec_acteur_obo(
    db_pool: asyncpg.Pool,
) -> None:
    """Un acteur OBO ayant accès au workspace n'accorde RIEN si le porteur de la
    clé n'y a pas accès — sinon forger l'en-tête acteur serait une élévation."""
    configure(db_pool)
    key_email = "obo-rights-key@test.local"
    human_email = "obo-rights-human@test.local"
    slug = "obo-rights-ws"
    try:
        key_id = await _insert_user(db_pool, subject="rights-key", email=key_email)
        human_id = await _insert_user(db_pool, subject="rights-human", email=human_email)
        await _insert_ws(db_pool, slug, owner_id=human_id)
        session = McpSession(
            user=_auth_user(key_id, key_email),
            api_key_scopes=[],
            api_key_admin=True,
            actor_user=_auth_user(human_id, human_email),
        )
        token = set_current_session(session)
        try:
            result = await _call_tool("list_documents", {"workspace_slug": slug})
            assert getattr(result, "isError", False) is True
            payload = json.loads(result.content[0].text)
            assert "accès refusé" in payload["error"]
        finally:
            reset_current_session(token)
    finally:
        await _cleanup(db_pool, slugs=[slug], emails=[key_email, human_email])


async def test_acces_accorde_si_porteur_a_acces_avec_acteur_obo(
    db_pool: asyncpg.Pool,
) -> None:
    """Non-régression : l'OBO ne restreint pas non plus — porteur owner → OK."""
    configure(db_pool)
    key_email = "obo-rights-key2@test.local"
    human_email = "obo-rights-human2@test.local"
    slug = "obo-rights-ws2"
    try:
        key_id = await _insert_user(db_pool, subject="rights-key2", email=key_email)
        human_id = await _insert_user(db_pool, subject="rights-human2", email=human_email)
        await _insert_ws(db_pool, slug, owner_id=key_id)
        session = McpSession(
            user=_auth_user(key_id, key_email),
            api_key_scopes=[],
            api_key_admin=True,
            actor_user=_auth_user(human_id, human_email),
        )
        token = set_current_session(session)
        try:
            result = await _call_tool("list_documents", {"workspace_slug": slug})
            assert not getattr(result, "isError", False)
        finally:
            reset_current_session(token)
    finally:
        await _cleanup(db_pool, slugs=[slug], emails=[key_email, human_email])


async def test_list_workspaces_visibilite_sur_le_porteur_pas_lacteur(
    db_pool: asyncpg.Pool,
) -> None:
    """La visibilité de list_workspaces suit le porteur de la clé, pas l'acteur."""
    configure(db_pool)
    key_email = "obo-vis-key@test.local"
    human_email = "obo-vis-human@test.local"
    ws_key_slug = "obo-vis-ws-porteur"
    ws_human_slug = "obo-vis-ws-acteur"
    try:
        key_id = await _insert_user(db_pool, subject="vis-key", email=key_email)
        human_id = await _insert_user(db_pool, subject="vis-human", email=human_email)
        await _insert_ws(db_pool, ws_key_slug, owner_id=key_id)
        await _insert_ws(db_pool, ws_human_slug, owner_id=human_id)
        session = McpSession(
            user=_auth_user(key_id, key_email),
            api_key_scopes=[],
            api_key_admin=True,
            actor_user=_auth_user(human_id, human_email),
        )
        token = set_current_session(session)
        try:
            result = await _call_tool("list_workspaces", {})
            slugs = {w["slug"] for w in json.loads(result[0].text)}
            assert ws_key_slug in slugs
            assert ws_human_slug not in slugs
        finally:
            reset_current_session(token)
    finally:
        await _cleanup(db_pool, slugs=[ws_key_slug, ws_human_slug], emails=[key_email, human_email])


# ── Attribution cohérente artefact / dataset / workspace ───────────────────────

_PNG = b"\x89PNG\r\n\x1a\n" + b"obo-fake-png"


def _artifact_settings() -> object:
    from docflow.config.settings import Settings

    return Settings(
        database_url="postgresql://unused/unused",
        jwt_secret="test-mcp-secret",  # type: ignore[arg-type]
        artifact_link_ttl_seconds=60,
    )


async def test_create_artifact_created_by_est_lhumain_obo(db_pool: asyncpg.Pool) -> None:
    import base64

    from docflow.mcp import artifact_tools

    configure(db_pool)
    key_email = "obo-art-key@test.local"
    human_email = "obo-art-human@test.local"
    slug = "obo-art-ws"
    try:
        key_id = await _insert_user(db_pool, subject="art-key", email=key_email)
        human_id = await _insert_user(db_pool, subject="art-human", email=human_email)
        await _insert_ws(db_pool, slug, owner_id=key_id)
        session = McpSession(
            user=_auth_user(key_id, key_email),
            api_key_scopes=[],
            api_key_admin=True,
            actor_user=_auth_user(human_id, human_email),
        )
        token = set_current_session(session)
        try:
            result = json.loads(
                (
                    await artifact_tools.handle_create_artifact(
                        db_pool,
                        _artifact_settings(),  # type: ignore[arg-type]
                        {
                            "workspace_slug": slug,
                            "filename": "obo.png",
                            "data_base64": base64.b64encode(_PNG).decode(),
                        },
                    )
                )[0].text
            )
            assert "error" not in result
            created_by = await db_pool.fetchval(
                "SELECT created_by FROM artifact WHERE id = $1", uuid.UUID(result["id"])
            )
            assert created_by == human_id
        finally:
            reset_current_session(token)
    finally:
        await _cleanup(db_pool, slugs=[slug], emails=[key_email, human_email])


async def test_create_artifact_created_by_est_la_cle_sans_obo(db_pool: asyncpg.Pool) -> None:
    import base64

    from docflow.mcp import artifact_tools

    configure(db_pool)
    key_email = "obo-art-key2@test.local"
    slug = "obo-art-ws2"
    try:
        key_id = await _insert_user(db_pool, subject="art-key2", email=key_email)
        await _insert_ws(db_pool, slug, owner_id=key_id)
        session = McpSession(
            user=_auth_user(key_id, key_email),
            api_key_scopes=[],
            api_key_admin=True,
            actor_user=None,
        )
        token = set_current_session(session)
        try:
            result = json.loads(
                (
                    await artifact_tools.handle_create_artifact(
                        db_pool,
                        _artifact_settings(),  # type: ignore[arg-type]
                        {
                            "workspace_slug": slug,
                            "filename": "obo2.png",
                            "data_base64": base64.b64encode(_PNG + b"2").decode(),
                        },
                    )
                )[0].text
            )
            assert "error" not in result
            created_by = await db_pool.fetchval(
                "SELECT created_by FROM artifact WHERE id = $1", uuid.UUID(result["id"])
            )
            assert created_by == key_id
        finally:
            reset_current_session(token)
    finally:
        await _cleanup(db_pool, slugs=[slug], emails=[key_email])


async def test_create_dataset_created_by_est_lhumain_obo(db_pool: asyncpg.Pool) -> None:
    from docflow.mcp import dataset_tools

    configure(db_pool)
    key_email = "obo-ds-key@test.local"
    human_email = "obo-ds-human@test.local"
    slug = "obo-ds-ws"
    try:
        key_id = await _insert_user(db_pool, subject="ds-key", email=key_email)
        human_id = await _insert_user(db_pool, subject="ds-human", email=human_email)
        await _insert_ws(db_pool, slug, owner_id=key_id)
        session = McpSession(
            user=_auth_user(key_id, key_email),
            api_key_scopes=[],
            api_key_admin=True,
            actor_user=_auth_user(human_id, human_email),
        )
        token = set_current_session(session)
        try:
            result = json.loads(
                (
                    await dataset_tools.handle(
                        "create_dataset",
                        db_pool,
                        {"workspace_slug": slug, "slug": "obo-ds", "label": "OBO DS"},
                    )
                )[0].text
            )
            assert "error" not in result
            created_by = await db_pool.fetchval(
                "SELECT created_by FROM dataset WHERE id = $1", uuid.UUID(result["id"])
            )
            assert created_by == human_id
        finally:
            reset_current_session(token)
    finally:
        await _cleanup(db_pool, slugs=[slug], emails=[key_email, human_email])

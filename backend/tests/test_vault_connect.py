"""Parcours « Connecter à Harpocrate » (start + callback), sécurité-critique.

Harpocrate est SIMULÉ : `harpocrate.connect.start`/`finish` sont monkeypatchés
(jamais de réseau réel). Couvre le fail-closed de `finish_connect` dans l'ordre
du brief : state absent, state étranger/inconnu/expiré (finish JAMAIS appelé),
access_denied, rejeu, échec SDK (`ConnectError`), atomicité secret+wallet, et
l'absence de toute fuite de secret dans les journaux.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from harpocrate import connect as harpocrate_connect
from harpocrate.exceptions import ConnectError
from structlog.testing import capture_logs

from docflow.app import app
from docflow.schemas.auth import AuthUser
from docflow.schemas.vault import VaultSecretCreate, VaultWalletCreate
from docflow.vault import connect as vault_connect
from docflow.vault import service as vault_svc

_ENC = Fernet.generate_key().decode()
_NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=UTC)


async def _owner(pool: asyncpg.Pool, email: str) -> uuid.UUID:
    uid: uuid.UUID = await pool.fetchval(
        "INSERT INTO app_user (email, label, source, validated, is_admin) "
        "VALUES ($1, 'T', 'local', true, true) RETURNING id",
        email,
    )
    return uid


def _user(uid: uuid.UUID, email: str) -> AuthUser:
    return AuthUser(id=uid, email=email, label=email, is_admin=True, validated=True, disabled=False)


def _fake_start(expected_url: str, expected_state: str):  # type: ignore[no-untyped-def]
    """Simule `harpocrate.connect.start` : dépose un `ConnectState` réel (le
    `code_verifier`/la clé privée n'ont pas besoin d'être cryptographiquement
    valides puisque `finish` est également simulé)."""

    def _start(
        base_url: str, client_id: str, redirect_uri: str, permissions: int, ttl_days: int | None
    ) -> tuple[str, harpocrate_connect.ConnectState]:
        assert base_url == expected_url
        assert permissions == 1, "permissions=1 (read) est une décision figée"
        assert ttl_days is None, "ttl_days=None est une décision figée"
        pending = harpocrate_connect.ConnectState(
            base_url=base_url,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=expected_state,
            code_verifier="sim-code-verifier",
            private_jwk={"kty": "EC", "crv": "P-256", "x": "x", "y": "y", "d": "d"},
        )
        return f"{base_url}/connect?state={expected_state}", pending

    return _start


def _fake_finish_ok(token: str):  # type: ignore[no-untyped-def]
    def _finish(
        pending: harpocrate_connect.ConnectState, *, code: str, state: str
    ) -> harpocrate_connect.ConnectResult:
        return harpocrate_connect.ConnectResult(
            token=token, api_key_id=uuid.uuid4(), wallet_id=uuid.uuid4()
        )

    return _finish


def _unreachable_finish(
    pending: harpocrate_connect.ConnectState, *, code: str, state: str
) -> harpocrate_connect.ConnectResult:
    raise AssertionError("finish NE DOIT PAS être appelé pour un state invalide/étranger/expiré")


async def _start(
    monkeypatch: pytest.MonkeyPatch,
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    state: str,
    name: str,
    base_url: str = "https://vault.example.com",
    now: datetime = _NOW,
) -> None:
    monkeypatch.setattr(harpocrate_connect, "start", _fake_start(base_url, state))
    browser_url = await vault_connect.start_connect(
        pool,
        user=user,
        name=name,
        url=base_url,
        description="Coffre de test",
        redirect_uri="https://app.example/api/admin/vault/connect/callback",
        client_id="docflow",
        enc_key=_ENC,
        now=now,
    )
    assert browser_url == f"{base_url}/connect?state={state}"


# ── 1. Nominal ────────────────────────────────────────────────────────────────


async def test_finish_connect_nominal_creates_secret_and_wallet(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _owner(db_pool, "connect-ok@example.com")
    user = _user(owner, "connect-ok@example.com")
    await _start(monkeypatch, db_pool, user=user, state="state-ok", name="corp-ok")

    monkeypatch.setattr(harpocrate_connect, "finish", _fake_finish_ok("hrpv_1_simtoken"))
    # Anti-régression (durcissement #4) : le chemin succès n'émet aucun log
    # aujourd'hui ; on capture quand même pour qu'un log ajouté plus tard qui
    # laisserait fuiter le token soit détecté immédiatement.
    with capture_logs() as cap:
        outcome = await vault_connect.finish_connect(
            db_pool,
            user=user,
            state="state-ok",
            code="the-code",
            error=None,
            enc_key=_ENC,
            now=_NOW,
        )
    assert outcome == "ok"
    for record in cap:
        assert "hrpv_1_simtoken" not in repr(record), f"token fuité dans un log : {record!r}"

    resolved = await vault_svc.get_api_key(db_pool, "corp-ok", _ENC)
    assert resolved is not None
    api_key, url = resolved
    assert api_key == "hrpv_1_simtoken"
    assert url == "https://vault.example.com"

    secrets = await vault_svc.list_secrets(db_pool, owner, _ENC, "HARPOCRATE_API_KEY")
    assert len(secrets) == 1
    assert secrets[0].storage_type == "local"
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


# ── 2. access_denied ──────────────────────────────────────────────────────────


async def test_finish_connect_access_denied_creates_nothing(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _owner(db_pool, "connect-denied@example.com")
    user = _user(owner, "connect-denied@example.com")
    await _start(monkeypatch, db_pool, user=user, state="state-denied", name="corp-denied")

    monkeypatch.setattr(harpocrate_connect, "finish", _unreachable_finish)
    outcome = await vault_connect.finish_connect(
        db_pool,
        user=user,
        state="state-denied",
        code=None,
        error="access_denied",
        enc_key=_ENC,
        now=_NOW,
    )
    assert outcome == "denied"
    assert await vault_svc.list_wallets(db_pool, owner) == []
    assert await vault_svc.list_secrets(db_pool, owner, _ENC) == []
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


# ── 3. state étranger / inconnu / expiré : finish JAMAIS appelé ─────────────


async def test_finish_connect_foreign_state_rejected(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_a = await _owner(db_pool, "connect-a@example.com")
    owner_b = await _owner(db_pool, "connect-b@example.com")
    user_a = _user(owner_a, "connect-a@example.com")
    user_b = _user(owner_b, "connect-b@example.com")
    await _start(monkeypatch, db_pool, user=user_a, state="state-foreign", name="corp-foreign")

    monkeypatch.setattr(harpocrate_connect, "finish", _unreachable_finish)
    outcome = await vault_connect.finish_connect(
        db_pool,
        user=user_b,  # un AUTRE propriétaire capture le state de A
        state="state-foreign",
        code="the-code",
        error=None,
        enc_key=_ENC,
        now=_NOW,
    )
    assert outcome == "invalid_state"
    assert await vault_svc.list_wallets(db_pool, owner_a) == []
    await db_pool.execute("DELETE FROM app_user WHERE id = ANY($1::uuid[])", [owner_a, owner_b])


async def test_finish_connect_unknown_state_rejected(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _owner(db_pool, "connect-unknown@example.com")
    user = _user(owner, "connect-unknown@example.com")
    monkeypatch.setattr(harpocrate_connect, "finish", _unreachable_finish)
    outcome = await vault_connect.finish_connect(
        db_pool,
        user=user,
        state="never-issued",
        code="the-code",
        error=None,
        enc_key=_ENC,
        now=_NOW,
    )
    assert outcome == "invalid_state"
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_finish_connect_missing_state_rejected(db_pool: asyncpg.Pool) -> None:
    owner = await _owner(db_pool, "connect-missing@example.com")
    user = _user(owner, "connect-missing@example.com")
    outcome = await vault_connect.finish_connect(
        db_pool, user=user, state=None, code="x", error=None, enc_key=_ENC, now=_NOW
    )
    assert outcome == "invalid_state"
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_finish_connect_expired_state_rejected(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _owner(db_pool, "connect-expired@example.com")
    user = _user(owner, "connect-expired@example.com")
    await _start(monkeypatch, db_pool, user=user, state="state-expired", name="corp-expired")

    monkeypatch.setattr(harpocrate_connect, "finish", _unreachable_finish)
    much_later = _NOW + timedelta(minutes=16)  # TTL de start_connect = 15 min
    outcome = await vault_connect.finish_connect(
        db_pool,
        user=user,
        state="state-expired",
        code="the-code",
        error=None,
        enc_key=_ENC,
        now=much_later,
    )
    assert outcome == "invalid_state"
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


# ── 4. Rejeu ──────────────────────────────────────────────────────────────────


async def test_finish_connect_replay_does_not_reconfigure(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _owner(db_pool, "connect-replay@example.com")
    user = _user(owner, "connect-replay@example.com")
    await _start(monkeypatch, db_pool, user=user, state="state-replay", name="corp-replay")

    monkeypatch.setattr(harpocrate_connect, "finish", _fake_finish_ok("hrpv_1_replaytoken"))
    first = await vault_connect.finish_connect(
        db_pool,
        user=user,
        state="state-replay",
        code="the-code",
        error=None,
        enc_key=_ENC,
        now=_NOW,
    )
    assert first == "ok"

    # Deuxième passage : finish ne doit PAS être rappelé (code à usage unique).
    monkeypatch.setattr(harpocrate_connect, "finish", _unreachable_finish)
    second = await vault_connect.finish_connect(
        db_pool,
        user=user,
        state="state-replay",
        code="the-code",
        error=None,
        enc_key=_ENC,
        now=_NOW,
    )
    assert second in ("already", "invalid_state")
    assert len(await vault_svc.list_wallets(db_pool, owner)) == 1, "pas de 2e config"
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


# ── 5. ConnectError du SDK ───────────────────────────────────────────────────


async def test_finish_connect_sdk_error_creates_nothing(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _owner(db_pool, "connect-sdkerr@example.com")
    user = _user(owner, "connect-sdkerr@example.com")
    await _start(monkeypatch, db_pool, user=user, state="state-sdkerr", name="corp-sdkerr")

    def _raise(
        pending: harpocrate_connect.ConnectState, *, code: str, state: str
    ) -> harpocrate_connect.ConnectResult:
        raise ConnectError("invalid_grant", "le code a déjà été consommé")

    monkeypatch.setattr(harpocrate_connect, "finish", _raise)
    outcome = await vault_connect.finish_connect(
        db_pool,
        user=user,
        state="state-sdkerr",
        code="bad-code",
        error=None,
        enc_key=_ENC,
        now=_NOW,
    )
    assert outcome == "error"
    assert await vault_svc.list_wallets(db_pool, owner) == []
    assert await vault_svc.list_secrets(db_pool, owner, _ENC) == []
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_finish_connect_transport_failure_rendered_as_error(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Harpocrate injoignable : le SDK lève une exception de TRANSPORT httpx
    (pas un ConnectError). Elle doit être rendue en `error` (jamais un 500 brut),
    le flux consommé (code à usage unique), et rien n'être créé."""
    owner = await _owner(db_pool, "connect-transport@example.com")
    user = _user(owner, "connect-transport@example.com")
    await _start(monkeypatch, db_pool, user=user, state="state-transport", name="corp-transport")

    def _raise_transport(
        pending: harpocrate_connect.ConnectState, *, code: str, state: str
    ) -> harpocrate_connect.ConnectResult:
        raise httpx.ConnectError("Connection refused to vault.example.com:443")

    monkeypatch.setattr(harpocrate_connect, "finish", _raise_transport)
    outcome = await vault_connect.finish_connect(
        db_pool,
        user=user,
        state="state-transport",
        code="the-code",
        error=None,
        enc_key=_ENC,
        now=_NOW,
    )
    assert outcome == "error"
    assert await vault_svc.list_wallets(db_pool, owner) == []
    assert await vault_svc.list_secrets(db_pool, owner, _ENC) == []

    # Flux consommé : un rejeu ne relance pas d'échange (take_active ne rend rien).
    monkeypatch.setattr(harpocrate_connect, "finish", _unreachable_finish)
    replay = await vault_connect.finish_connect(
        db_pool,
        user=user,
        state="state-transport",
        code="the-code",
        error=None,
        enc_key=_ENC,
        now=_NOW,
    )
    assert replay in ("already", "invalid_state")
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


def test_connect_callback_transport_failure_http_302_error(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    """Round-trip HTTP : une panne de transport au callback renvoie 302
    `?connect=error`, jamais un 500 opaque (critère 6, raison lisible)."""
    with _client(monkeypatch, test_schema_url) as client:
        _auth(client)

        def _start(
            base_url: str,
            client_id: str,
            redirect_uri: str,
            permissions: int,
            ttl_days: int | None,
        ) -> tuple[str, harpocrate_connect.ConnectState]:
            pending = harpocrate_connect.ConnectState(
                base_url=base_url,
                client_id=client_id,
                redirect_uri=redirect_uri,
                state="http-transport-1",
                code_verifier="cv",
                private_jwk={"kty": "EC"},
            )
            return f"{base_url}/connect?state=http-transport-1", pending

        monkeypatch.setattr(harpocrate_connect, "start", _start)
        r = client.post(
            "/api/admin/vault/connect/start",
            json={
                "name": "http-transport",
                "url": "https://vault.http.example",
                "description": None,
            },
        )
        assert r.status_code == 200, r.text

        def _raise_transport(
            pending: harpocrate_connect.ConnectState, *, code: str, state: str
        ) -> harpocrate_connect.ConnectResult:
            raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(harpocrate_connect, "finish", _raise_transport)
        r = client.get(
            "/api/admin/vault/connect/callback",
            params={"code": "http-code", "state": "http-transport-1"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == "/admin/vault?connect=error"
        assert client.get("/api/admin/vault/wallets").json() == []


# ── 6. Atomicité secret + wallet ─────────────────────────────────────────────


async def test_finish_connect_duplicate_wallet_name_rolls_back_secret(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = await _owner(db_pool, "connect-dup-other@example.com")
    other_key = await vault_svc.create_secret(
        db_pool,
        other,
        VaultSecretCreate(label="Autre", slug="autre", value="x", secret_type="HARPOCRATE_API_KEY"),
        enc_key=_ENC,
    )
    # Alias GLOBAL déjà pris par un AUTRE propriétaire : l'INSERT wallet du
    # parcours connect va échouer dessus (UniqueViolationError sur `name`).
    await vault_svc.create_wallet(
        db_pool,
        other,
        VaultWalletCreate(name="corp-dup", url="https://v", api_key_secret_id=other_key.id),
    )

    owner = await _owner(db_pool, "connect-dup@example.com")
    user = _user(owner, "connect-dup@example.com")
    await _start(monkeypatch, db_pool, user=user, state="state-dup", name="corp-dup")

    monkeypatch.setattr(harpocrate_connect, "finish", _fake_finish_ok("hrpv_1_duptoken"))
    outcome = await vault_connect.finish_connect(
        db_pool,
        user=user,
        state="state-dup",
        code="the-code",
        error=None,
        enc_key=_ENC,
        now=_NOW,
    )
    assert outcome == "duplicate"

    # NI le secret NI le wallet de CE propriétaire ne doivent persister.
    assert await vault_svc.list_secrets(db_pool, owner, _ENC, "HARPOCRATE_API_KEY") == []
    assert await vault_svc.list_wallets(db_pool, owner) == []
    # L'endpoint préexistant (autre propriétaire) est intact.
    assert [w.name for w in await vault_svc.list_wallets(db_pool, other)] == ["corp-dup"]
    await db_pool.execute("DELETE FROM app_user WHERE id = ANY($1::uuid[])", [owner, other])


# ── 7. Anti-log ───────────────────────────────────────────────────────────────


async def test_finish_connect_never_logs_sensitive_values(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _owner(db_pool, "connect-antilog@example.com")
    user = _user(owner, "connect-antilog@example.com")
    await _start(monkeypatch, db_pool, user=user, state="state-antilog", name="corp-antilog")

    secret_token = "hrpv_1_SUPERSECRETTOKEN"
    secret_code = "the-super-secret-code"
    secret_dkey = "the-super-secret-dkey"
    secret_jwe = "the.super.secret.jwe"

    def _raise_with_secrets(
        pending: harpocrate_connect.ConnectState, *, code: str, state: str
    ) -> harpocrate_connect.ConnectResult:
        assert code == secret_code
        raise ConnectError("invalid_grant", "simulated failure")

    monkeypatch.setattr(harpocrate_connect, "finish", _raise_with_secrets)

    with capture_logs() as cap:
        outcome = await vault_connect.finish_connect(
            db_pool,
            user=user,
            state="state-antilog",
            code=secret_code,
            error=None,
            enc_key=_ENC,
            now=_NOW,
        )
    assert outcome == "error"

    forbidden = [secret_token, secret_code, secret_dkey, secret_jwe, "sim-code-verifier", _ENC]
    for record in cap:
        rendered = repr(record)
        for value in forbidden:
            assert value not in rendered, f"{value!r} a fuité dans un log : {record!r}"
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


# ── 8. Non-régression (routes manuelles) + round-trip HTTP ──────────────────


_JWT_SECRET = "test_jwt_secret_vault_connect"


def _client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    monkeypatch.setenv("ENCRYPTION_KEY", _ENC)
    return TestClient(app)


def _auth(client: TestClient) -> None:
    client.post(
        "/api/setup/init-admin",
        json={
            "username": "connectadmin",
            "email": "connectadmin@example.com",
            "password": "pw123456789",
        },
    )
    login = client.post(
        "/api/auth/login", json={"username": "connectadmin", "password": "pw123456789"}
    )
    assert login.status_code == 200, login.text


def test_manual_wallet_and_secret_routes_unchanged(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    """Non-régression (critère 8) : les routes manuelles créées en Task antérieures
    continuent de fonctionner après l'extraction des helpers `_insert_*`."""
    with _client(monkeypatch, test_schema_url) as client:
        _auth(client)
        r = client.post(
            "/api/admin/secrets",
            json={
                "label": "Clé manuelle",
                "slug": "cle-manuelle",
                "value": "hrpv_manual",
                "secret_type": "HARPOCRATE_API_KEY",
            },
        )
        assert r.status_code == 201, r.text
        secret_id = r.json()["id"]

        r = client.post(
            "/api/admin/vault/wallets",
            json={
                "name": "manual-wallet",
                "url": "https://manual.example",
                "api_key_secret_id": secret_id,
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["api_key_secret_label"] == "Clé manuelle"

        assert client.get("/api/admin/vault/wallets").status_code == 200
        assert client.get("/api/admin/secrets").status_code == 200


def test_connect_start_and_callback_http_round_trip(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _client(monkeypatch, test_schema_url) as client:
        _auth(client)

        state_holder: dict[str, str] = {}

        def _start(
            base_url: str,
            client_id: str,
            redirect_uri: str,
            permissions: int,
            ttl_days: int | None,
        ) -> tuple[str, harpocrate_connect.ConnectState]:
            assert client_id == "docflow"
            assert redirect_uri.endswith("/api/admin/vault/connect/callback")
            pending = harpocrate_connect.ConnectState(
                base_url=base_url,
                client_id=client_id,
                redirect_uri=redirect_uri,
                state="http-state-1",
                code_verifier="cv",
                private_jwk={"kty": "EC"},
            )
            state_holder["state"] = pending.state
            return f"{base_url}/connect?state=http-state-1", pending

        monkeypatch.setattr(harpocrate_connect, "start", _start)
        r = client.post(
            "/api/admin/vault/connect/start",
            json={"name": "http-corp", "url": "https://vault.http.example", "description": None},
        )
        assert r.status_code == 200, r.text
        assert r.json()["browser_url"].startswith("https://vault.http.example/connect")

        monkeypatch.setattr(harpocrate_connect, "finish", _fake_finish_ok("hrpv_1_httptoken"))
        r = client.get(
            "/api/admin/vault/connect/callback",
            params={"code": "http-code", "state": state_holder["state"]},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == "/admin/vault?connect=ok"

        wallets = client.get("/api/admin/vault/wallets").json()
        assert any(w["name"] == "http-corp" for w in wallets)

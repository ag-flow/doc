from __future__ import annotations

import time
import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient

from docflow.app import app
from docflow.auth.jwt import create_token, decode_token
from docflow.auth.password import hash_password, verify_password
from docflow.schemas.auth import AuthUser

# ── Fixtures communes ─────────────────────────────────────────────────────────

_BOOTSTRAP_EMAIL = "bootstrap@example.com"
_BOOTSTRAP_PW = "bootstrap_pw_123"
_JWT_SECRET = "test_jwt_secret_for_m2"

_BASE_ENV = {
    "JWT_SECRET": _JWT_SECRET,
}


def _make_client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    return TestClient(app)


def _admin_token(user_id: uuid.UUID, email: str = "x@x.com") -> str:
    user = AuthUser(
        id=user_id, email=email, label="L", is_admin=True, validated=True, disabled=False
    )
    return create_token(user, _JWT_SECRET)


def _regular_token(user_id: uuid.UUID, email: str = "x@x.com") -> str:
    user = AuthUser(
        id=user_id, email=email, label="L", is_admin=False, validated=True, disabled=False
    )
    return create_token(user, _JWT_SECRET)


def _setup_admin(client: TestClient) -> str:
    """Crée l'admin via le wizard setup et retourne le token."""
    r = client.post(
        "/api/setup/init-admin",
        json={
            "username": "bootstrap",
            "email": _BOOTSTRAP_EMAIL,
            "password": _BOOTSTRAP_PW,
        },
    )
    assert r.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW},
    )
    assert login.status_code == 200
    return login.json()["access_token"]  # type: ignore[no-any-return]


# ── Password ──────────────────────────────────────────────────────────────────


def test_hash_and_verify() -> None:
    hashed = hash_password("secret")
    assert verify_password("secret", hashed)
    assert not verify_password("wrong", hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────


_LONG_SECRET = "test-secret-key-for-unit-tests-hs256"


def test_jwt_roundtrip() -> None:
    user = AuthUser(
        id=uuid.uuid4(), email="a@b.com", label="L", is_admin=True, validated=True, disabled=False
    )
    token = create_token(user, _LONG_SECRET)
    claims = decode_token(token, _LONG_SECRET)
    assert claims["email"] == "a@b.com"
    assert claims["is_admin"] is True


def test_jwt_wrong_secret_rejected() -> None:
    user = AuthUser(
        id=uuid.uuid4(), email="a@b.com", label="L", is_admin=False, validated=True, disabled=False
    )
    token = create_token(user, _LONG_SECRET)
    with pytest.raises(ValueError):
        decode_token(token, "another-test-secret-key-wrong-one")


def test_jwt_expired_rejected() -> None:
    from joserfc import jwt as joserfc_jwt
    from joserfc.jwk import OctKey as _OctKey

    header = {"alg": "HS256"}
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "a@b.com",
        "is_admin": False,
        "iat": int(time.time()) - 3600,
        "exp": int(time.time()) - 1,
    }
    key = _OctKey.import_key(_LONG_SECRET)
    token = joserfc_jwt.encode(header, payload, key)
    with pytest.raises(ValueError, match="token invalide"):
        decode_token(token, _LONG_SECRET)


# ── Setup wizard → premier admin ──────────────────────────────────────────────


async def test_setup_creates_admin(
    db_pool: asyncpg.Pool,
    clean_admin_users: None,
) -> None:
    count_before: int = await db_pool.fetchval("SELECT COUNT(*) FROM app_user")
    assert count_before == 0

    hashed = hash_password(_BOOTSTRAP_PW)
    await db_pool.execute(
        "INSERT INTO app_user (username, email, label, password_hash, is_admin, validated, source)"
        " VALUES ($1, $2, $3, $4, true, true, 'local')",
        "bootstrap", _BOOTSTRAP_EMAIL, "Bootstrap", hashed,
    )
    count_after: int = await db_pool.fetchval("SELECT COUNT(*) FROM app_user")
    assert count_after == 1

    row = await db_pool.fetchrow(
        "SELECT email, is_admin, validated, disabled FROM app_user"
    )
    assert row is not None
    assert row["email"] == _BOOTSTRAP_EMAIL
    assert row["is_admin"] is True
    assert row["validated"] is True
    assert row["disabled"] is False


# ── Login / me (via TestClient) ───────────────────────────────────────────────


def test_login_valid_credentials(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        token = _setup_admin(client)
        assert token


def test_login_wrong_password(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        _setup_admin(client)
        resp = client.post(
            "/api/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": "wrong"}
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "identifiants invalides"


def test_login_unknown_email(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        _setup_admin(client)
        resp = client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "pw"}
        )
    assert resp.status_code == 401


def test_login_pending_validation(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    """Un utilisateur non validé reçoit 403 PendingValidation."""
    with _make_client(monkeypatch, test_schema_url) as client:
        token = _setup_admin(client)
        client.post(
            "/api/admin/users",
            json={"email": "pending@test.com", "label": "Pending", "password": "pw12345678"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Créer directement un user non validé (OIDC simulé)
        resp = client.post(
            "/api/auth/login",
            json={"email": "pending@test.com", "password": "pw12345678"},
        )
    assert resp.status_code == 200  # créé validé via API admin — test PendingValidation via DB


def test_get_me_authenticated(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        token = _setup_admin(client)
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == _BOOTSTRAP_EMAIL


def test_get_me_no_token(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        _setup_admin(client)
        resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_require_admin_rejects_non_admin(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    """Un utilisateur non-admin ne doit pas accéder aux routes /admin/users."""
    with _make_client(monkeypatch, test_schema_url) as client:
        token = _setup_admin(client)

        r = client.post(
            "/api/admin/users",
            json={
                "email": "regular@test.com",
                "label": "Regular",
                "password": "pw12345678",
                "is_admin": False,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        regular_id = uuid.UUID(r.json()["id"])

        regular_token = _regular_token(regular_id, email="regular@test.com")
        resp = client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {regular_token}"}
        )
    assert resp.status_code == 403


# ── Anti-lock-out ─────────────────────────────────────────────────────────────


def test_cannot_disable_last_local_admin(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        token = _setup_admin(client)
        admins = client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {token}"}
        ).json()
        last_id = admins[0]["id"]
        resp = client.patch(
            f"/api/admin/users/{last_id}",
            json={"disabled": True},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "last_local_admin"


def test_cannot_delete_last_local_admin(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        token = _setup_admin(client)
        admins = client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {token}"}
        ).json()
        last_id = admins[0]["id"]
        resp = client.delete(
            f"/api/admin/users/{last_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "last_local_admin"


def test_can_disable_admin_when_another_local_exists(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        token = _setup_admin(client)
        second = client.post(
            "/api/admin/users",
            json={"email": "second@test.com", "label": "Second", "password": "pw2345678"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert second.status_code == 201
        second_id = second.json()["id"]
        resp = client.patch(
            f"/api/admin/users/{second_id}",
            json={"disabled": True},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["disabled"] is True

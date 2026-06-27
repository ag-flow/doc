from __future__ import annotations

import time
import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient

from docflow.app import app
from docflow.auth.jwt import create_token, decode_token
from docflow.auth.password import hash_password, verify_password
from docflow.auth.seed import seed_bootstrap_admin
from docflow.schemas.auth import AuthUser

# ── Fixtures communes ─────────────────────────────────────────────────────────

_BOOTSTRAP_EMAIL = "bootstrap@example.com"
_BOOTSTRAP_PW = "bootstrap_pw_123"
_JWT_SECRET = "test_jwt_secret_for_m2"

_BASE_ENV = {
    "ADMIN_EMAIL": _BOOTSTRAP_EMAIL,
    "ADMIN_PASSWORD": _BOOTSTRAP_PW,
    "JWT_SECRET": _JWT_SECRET,
}


def _make_client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    return TestClient(app)


def _superadmin_token(user_id: uuid.UUID, email: str = "x@x.com") -> str:
    user = AuthUser(id=user_id, email=email, label="L", is_superadmin=True, disabled=False)
    return create_token(user, _JWT_SECRET)


def _regular_token(user_id: uuid.UUID, email: str = "x@x.com") -> str:
    user = AuthUser(id=user_id, email=email, label="L", is_superadmin=False, disabled=False)
    return create_token(user, _JWT_SECRET)


# ── Password ──────────────────────────────────────────────────────────────────


def test_hash_and_verify() -> None:
    hashed = hash_password("secret")
    assert verify_password("secret", hashed)
    assert not verify_password("wrong", hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────


_LONG_SECRET = "test-secret-key-for-unit-tests-hs256"  # >= 112 bits


def test_jwt_roundtrip() -> None:
    user = AuthUser(
        id=uuid.uuid4(), email="a@b.com", label="L", is_superadmin=True, disabled=False
    )
    token = create_token(user, _LONG_SECRET)
    claims = decode_token(token, _LONG_SECRET)
    assert claims["email"] == "a@b.com"
    assert claims["is_superadmin"] is True


def test_jwt_wrong_secret_rejected() -> None:
    user = AuthUser(
        id=uuid.uuid4(), email="a@b.com", label="L", is_superadmin=False, disabled=False
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
        "is_superadmin": False,
        "iat": int(time.time()) - 3600,
        "exp": int(time.time()) - 1,  # déjà expiré
    }
    key = _OctKey.import_key(_LONG_SECRET)
    token = joserfc_jwt.encode(header, payload, key)
    with pytest.raises(ValueError, match="token invalide"):
        decode_token(token, _LONG_SECRET)


# ── Seed bootstrap ────────────────────────────────────────────────────────────


async def test_seed_creates_admin_on_empty_db(
    db_pool: asyncpg.Pool,
    clean_admin_users: None,
) -> None:
    from docflow.config.settings import Settings

    settings = Settings(
        database_url="x",
        admin_email=_BOOTSTRAP_EMAIL,
        admin_password=_BOOTSTRAP_PW,
        jwt_secret=_JWT_SECRET,
    )
    await seed_bootstrap_admin(db_pool, settings)

    count = await db_pool.fetchval("SELECT COUNT(*) FROM admin_user")
    assert count == 1

    row = await db_pool.fetchrow("SELECT email, is_superadmin, disabled FROM admin_user")
    assert row["email"] == _BOOTSTRAP_EMAIL
    assert row["is_superadmin"] is True
    assert row["disabled"] is False


async def test_seed_is_idempotent(
    db_pool: asyncpg.Pool,
    clean_admin_users: None,
) -> None:
    from docflow.config.settings import Settings

    settings = Settings(
        database_url="x",
        admin_email=_BOOTSTRAP_EMAIL,
        admin_password=_BOOTSTRAP_PW,
        jwt_secret=_JWT_SECRET,
    )
    await seed_bootstrap_admin(db_pool, settings)
    await seed_bootstrap_admin(db_pool, settings)

    count = await db_pool.fetchval("SELECT COUNT(*) FROM admin_user")
    assert count == 1


async def test_seed_password_not_in_log(
    db_pool: asyncpg.Pool,
    clean_admin_users: None,
    capfd: pytest.CaptureFixture[str],
) -> None:
    from docflow.config.settings import Settings

    settings = Settings(
        database_url="x",
        admin_email="admin@log-test.com",
        admin_password="DO_NOT_LOG_THIS_PW",
        jwt_secret="s",
    )
    await seed_bootstrap_admin(db_pool, settings)
    captured = capfd.readouterr()
    assert "DO_NOT_LOG_THIS_PW" not in captured.out
    assert "DO_NOT_LOG_THIS_PW" not in captured.err


# ── Login / me (via TestClient) ───────────────────────────────────────────────


def test_login_valid_credentials(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        resp = client.post(
            "/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        resp = client.post(
            "/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": "wrong"}
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "identifiants invalides"


def test_login_unknown_email(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        resp = client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": "pw"}
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "identifiants invalides"


def test_login_disabled_user(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    """Créer un 2e admin via l'API, le désactiver, puis vérifier le login est refusé."""
    with _make_client(monkeypatch, test_schema_url) as client:
        # Login en tant que bootstrap pour avoir le token
        login = client.post(
            "/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
        token = login.json()["access_token"]

        # Créer un 2e admin
        r = client.post(
            "/admin/users",
            json={"email": "disabled@test.com", "label": "ToDisable", "password": "pw123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        second_id = r.json()["id"]

        # Le désactiver
        client.patch(
            f"/admin/users/{second_id}",
            json={"disabled": True},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Tenter le login → doit échouer
        resp = client.post(
            "/auth/login", json={"email": "disabled@test.com", "password": "pw123"}
        )
    assert resp.status_code == 401


def test_get_me_authenticated(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        login = client.post(
            "/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
        token = login.json()["access_token"]
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == _BOOTSTRAP_EMAIL


def test_get_me_no_token(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_require_superadmin_rejects_non_superadmin(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    """Un admin non-superadmin ne doit pas accéder aux routes /admin/users."""
    with _make_client(monkeypatch, test_schema_url) as client:
        # Créer un admin non-superadmin via l'API
        login = client.post(
            "/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
        token = login.json()["access_token"]

        r = client.post(
            "/admin/users",
            json={
                "email": "regular@test.com",
                "label": "Regular",
                "password": "pw",
                "is_superadmin": False,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        regular_id = uuid.UUID(r.json()["id"])

        # Créer un token pour cet admin non-superadmin
        regular_token = _regular_token(regular_id, email="regular@test.com")

        resp = client.get(
            "/admin/users", headers={"Authorization": f"Bearer {regular_token}"}
        )
    assert resp.status_code == 403


# ── Anti-lock-out ─────────────────────────────────────────────────────────────


def test_cannot_disable_last_local_admin(
    monkeypatch: pytest.MonkeyPatch,
    test_schema_url: str,
    clean_admin_users: None,
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        login = client.post(
            "/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
        token = login.json()["access_token"]

        admins = client.get(
            "/admin/users", headers={"Authorization": f"Bearer {token}"}
        ).json()
        last_id = admins[0]["id"]

        resp = client.patch(
            f"/admin/users/{last_id}",
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
        login = client.post(
            "/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
        token = login.json()["access_token"]

        admins = client.get(
            "/admin/users", headers={"Authorization": f"Bearer {token}"}
        ).json()
        last_id = admins[0]["id"]

        resp = client.delete(
            f"/admin/users/{last_id}",
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
        login = client.post(
            "/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
        token = login.json()["access_token"]

        second = client.post(
            "/admin/users",
            json={"email": "second@test.com", "label": "Second", "password": "pw2"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert second.status_code == 201
        second_id = second.json()["id"]

        resp = client.patch(
            f"/admin/users/{second_id}",
            json={"disabled": True},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["disabled"] is True

from __future__ import annotations

import asyncpg
import pytest
from fastapi.testclient import TestClient

from docflow.app import app
from docflow.auth.password import hash_password, verify_password

# ── Fixtures communes ─────────────────────────────────────────────────────────

_BOOTSTRAP_EMAIL = "bootstrap@example.com"
_BOOTSTRAP_PW = "bootstrap_pw_123"
_JWT_SECRET = "test_jwt_secret_for_m2"
_SESSION_COOKIE = "docflow_session"

_BASE_ENV = {"JWT_SECRET": _JWT_SECRET}


def _make_client(monkeypatch: pytest.MonkeyPatch, test_schema_url: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_schema_url)
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    return TestClient(app)


def _login_cookies(client: TestClient, email: str, pw: str) -> dict[str, str]:
    """Loggue et rend un dict cookies {docflow_session: token}, jar client vidé —
    auth explicite par requête (multi-identité sûre)."""
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    token = client.cookies.get(_SESSION_COOKIE)
    client.cookies.clear()
    return {_SESSION_COOKIE: token}


def _setup_admin(client: TestClient) -> dict[str, str]:
    """Crée l'admin via le wizard setup et retourne ses cookies de session."""
    r = client.post(
        "/api/setup/init-admin",
        json={"username": "bootstrap", "email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW},
    )
    assert r.status_code == 201
    return _login_cookies(client, _BOOTSTRAP_EMAIL, _BOOTSTRAP_PW)


# ── Password ──────────────────────────────────────────────────────────────────


def test_hash_and_verify() -> None:
    hashed = hash_password("secret")
    assert verify_password("secret", hashed)
    assert not verify_password("wrong", hashed)


# ── Setup wizard → premier admin ──────────────────────────────────────────────


async def test_setup_creates_admin(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    count_before: int = await db_pool.fetchval("SELECT COUNT(*) FROM app_user")
    assert count_before == 0

    hashed = hash_password(_BOOTSTRAP_PW)
    await db_pool.execute(
        "INSERT INTO app_user (username, email, label, password_hash, is_admin, validated, source)"
        " VALUES ($1, $2, $3, $4, true, true, 'local')",
        "bootstrap",
        _BOOTSTRAP_EMAIL,
        "Bootstrap",
        hashed,
    )
    count_after: int = await db_pool.fetchval("SELECT COUNT(*) FROM app_user")
    assert count_after == 1

    row = await db_pool.fetchrow("SELECT email, is_admin, validated, disabled FROM app_user")
    assert row is not None
    assert row["email"] == _BOOTSTRAP_EMAIL
    assert row["is_admin"] is True
    assert row["validated"] is True
    assert row["disabled"] is False


# ── Login / me / logout (session serveur + cookie) ────────────────────────────


def test_login_pose_un_cookie_de_session(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        client.post(
            "/api/setup/init-admin",
            json={"username": "bootstrap", "email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW},
        )
        r = client.post(
            "/api/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
        assert r.status_code == 200
        # Le corps porte le profil (plus de jeton) ; l'auth est dans le cookie.
        assert r.json()["email"] == _BOOTSTRAP_EMAIL
        assert "access_token" not in r.json()
        assert client.cookies.get(_SESSION_COOKIE)


def test_login_wrong_password(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        _setup_admin(client)
        resp = client.post("/api/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "identifiants invalides"


def test_login_unknown_email(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        _setup_admin(client)
        resp = client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "pw"}
        )
    assert resp.status_code == 401


def test_get_me_authenticated(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        admin = _setup_admin(client)
        resp = client.get("/api/auth/me", cookies=admin)
    assert resp.status_code == 200
    assert resp.json()["email"] == _BOOTSTRAP_EMAIL


def test_get_me_no_cookie(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        _setup_admin(client)
        resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_logout_revoque_la_session_cote_serveur(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    """Le cœur de la fiche : après logout, un cookie COPIÉ avant cesse de valoir —
    la session est révoquée en base, pas seulement le cookie retiré du navigateur."""
    with _make_client(monkeypatch, test_schema_url) as client:
        admin = _setup_admin(client)  # copie du cookie, jar vidé
        # Le cookie fonctionne.
        assert client.get("/api/auth/me", cookies=admin).status_code == 200
        # Déconnexion (le serveur révoque la session portée par ce cookie).
        assert client.post("/api/auth/logout", cookies=admin).status_code == 204
        # Le même cookie copié est désormais refusé.
        assert client.get("/api/auth/me", cookies=admin).status_code == 401


def test_bearer_est_traite_comme_cle_api(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    """docflow n'émet plus de jeton porteur : tout Authorization: Bearer est une
    clé API. Un ex-JWT (ou tout bearer inconnu) est donc refusé « clé API invalide »
    — un jeton destiné à un autre module de la stack ne franchit pas docflow."""
    with _make_client(monkeypatch, test_schema_url) as client:
        _setup_admin(client)
        for raw in ("mcpk_inconnu", "dfk_inconnu", "a.b.c", "nimportequoi"):
            resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"})
            assert resp.status_code == 401, raw
            assert resp.json()["detail"] == "clé API invalide ou révoquée", raw


def test_require_superadmin_rejects_non_admin(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    """Un utilisateur non-admin ne doit pas accéder aux routes /admin/users."""
    with _make_client(monkeypatch, test_schema_url) as client:
        admin = _setup_admin(client)
        r = client.post(
            "/api/admin/users",
            json={
                "email": "regular@test.com",
                "label": "Regular",
                "password": "pw12345678",
                "is_admin": False,
            },
            cookies=admin,
        )
        assert r.status_code == 201
        regular = _login_cookies(client, "regular@test.com", "pw12345678")
        resp = client.get("/api/admin/users", cookies=regular)
    assert resp.status_code == 403


def test_admin_revoque_les_sessions_d_un_utilisateur(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    """Révocation par un admin (compromission) : toutes les sessions de la cible
    cessent immédiatement de valoir, sans redémarrage."""
    with _make_client(monkeypatch, test_schema_url) as client:
        admin = _setup_admin(client)
        created = client.post(
            "/api/admin/users",
            json={"email": "victim@test.com", "label": "V", "password": "pw12345678"},
            cookies=admin,
        )
        assert created.status_code == 201
        victim_id = created.json()["id"]
        victim = _login_cookies(client, "victim@test.com", "pw12345678")
        assert client.get("/api/auth/me", cookies=victim).status_code == 200

        revoke = client.post(f"/api/admin/users/{victim_id}/sessions/revoke", cookies=admin)
        assert revoke.status_code == 200
        assert revoke.json()["revoked"] >= 1
        # La session de la victime est coupée immédiatement.
        assert client.get("/api/auth/me", cookies=victim).status_code == 401


# ── Anti-lock-out ─────────────────────────────────────────────────────────────


def test_cannot_disable_last_local_admin(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        admin = _setup_admin(client)
        admins = client.get("/api/admin/users", cookies=admin).json()
        last_id = admins[0]["id"]
        resp = client.patch(
            f"/api/admin/users/{last_id}", json={"disabled": True}, cookies=admin
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "last_local_admin"


def test_cannot_delete_last_local_admin(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        admin = _setup_admin(client)
        admins = client.get("/api/admin/users", cookies=admin).json()
        last_id = admins[0]["id"]
        resp = client.delete(f"/api/admin/users/{last_id}", cookies=admin)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "last_local_admin"


def test_can_disable_admin_when_another_local_exists(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    with _make_client(monkeypatch, test_schema_url) as client:
        admin = _setup_admin(client)
        second = client.post(
            "/api/admin/users",
            json={"email": "second@test.com", "label": "Second", "password": "pw2345678"},
            cookies=admin,
        )
        assert second.status_code == 201
        second_id = second.json()["id"]
        resp = client.patch(
            f"/api/admin/users/{second_id}", json={"disabled": True}, cookies=admin
        )
    assert resp.status_code == 200
    assert resp.json()["disabled"] is True


def test_local_login_disabled_flag(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    """LOCAL_LOGIN_ENABLED=false : mire sans connexion locale, /auth/login en 403.
    Ignoré tant qu'aucun utilisateur n'existe (le wizard doit rester possible)."""
    monkeypatch.setenv("LOCAL_LOGIN_ENABLED", "false")
    with _make_client(monkeypatch, test_schema_url) as client:
        m = client.get("/api/auth/methods").json()
        assert m["local"] is True
        assert m["needs_setup"] is True

        r = client.post(
            "/api/setup/init-admin",
            json={"username": "bootstrap", "email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW},
        )
        assert r.status_code in (200, 201)

        m = client.get("/api/auth/methods").json()
        assert m["local"] is False
        r = client.post(
            "/api/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
        assert r.status_code == 403
        assert "désactivée" in r.json()["detail"]


def test_oidc_only_via_config_and_reactivation(
    monkeypatch: pytest.MonkeyPatch, test_schema_url: str, clean_admin_users: None
) -> None:
    """Le flag de la page OIDC ne désactive le local QUE si l'OIDC est activé ;
    désactiver l'OIDC réactive automatiquement la connexion locale."""
    with _make_client(monkeypatch, test_schema_url) as client:
        admin = _setup_admin(client)
        body = {
            "issuer": "https://issuer.example.com",
            "client_id": "docflow",
            "client_secret_ref": "inline-secret",
            "enabled": False,
            "disable_local_login": True,
        }
        assert client.put("/api/admin/oidc", json=body, cookies=admin).status_code == 200
        assert client.get("/api/auth/methods").json()["local"] is True

        body["enabled"] = True
        client.put("/api/admin/oidc", json=body, cookies=admin)
        assert client.get("/api/auth/methods").json()["local"] is False
        r = client.post(
            "/api/auth/login", json={"email": _BOOTSTRAP_EMAIL, "password": _BOOTSTRAP_PW}
        )
        assert r.status_code == 403

        body["enabled"] = False
        client.put("/api/admin/oidc", json=body, cookies=admin)
        assert client.get("/api/auth/methods").json()["local"] is True

        body["enabled"] = True
        client.put("/api/admin/oidc", json=body, cookies=admin)

    try:
        monkeypatch.setenv("LOCAL_LOGIN_ENABLED", "true")
        with _make_client(monkeypatch, test_schema_url) as client:
            assert client.get("/api/auth/methods").json()["local"] is True
    finally:
        monkeypatch.delenv("LOCAL_LOGIN_ENABLED", raising=False)
        with _make_client(monkeypatch, test_schema_url) as client:
            body["enabled"] = False
            body["disable_local_login"] = False
            client.put("/api/admin/oidc", json=body, cookies=admin)

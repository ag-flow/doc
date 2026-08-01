"""Autorisations des outils MCP selon la session (JWT vs clé API scopée)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import asyncpg
import pytest

from docflow.apikeys.schemas import ApiProfileScopeOut
from docflow.mcp.server import _call_tool, _check_tool_authz, configure
from docflow.mcp.session import McpSession, reset_current_session, set_current_session
from docflow.schemas.auth import AuthUser

_WS = "test-ws"


def _user(*, is_admin: bool = False) -> AuthUser:
    return AuthUser(
        id=uuid.uuid4(),
        email="mcp@test.local",
        label="mcp",
        is_admin=is_admin,
        validated=True,
        disabled=False,
    )


def _scope(ws: str, *, block: str | None = None, read_only: bool = False) -> ApiProfileScopeOut:
    return ApiProfileScopeOut(
        id=uuid.uuid4(), workspace_slug=ws, block_slug=block, read_only=read_only
    )


@pytest.fixture()
def jwt_session() -> Iterator[McpSession]:
    session = McpSession(user=_user())
    token = set_current_session(session)
    yield session
    reset_current_session(token)


def _use_session(session: McpSession) -> tuple[McpSession, object]:
    return session, set_current_session(session)


# ── _check_tool_authz : unités ────────────────────────────────────────────────


def test_jwt_session_sans_restriction(jwt_session: McpSession) -> None:
    """Session JWT : aucun outil n'est restreint (comportement actuel conservé)."""
    assert _check_tool_authz("create_workspace", {}) is None
    assert _check_tool_authz("create_document", {"workspace_slug": _WS}) is None
    assert _check_tool_authz("generate_api_key", {}) is None


def test_session_absente_sans_restriction() -> None:
    """Pas de session (appel interne/tests) : la garde HTTP a déjà authentifié."""
    assert _check_tool_authz("create_workspace", {}) is None


def test_cle_admin_sans_restriction() -> None:
    session, token = _use_session(McpSession(user=_user(), api_key_scopes=[], api_key_admin=True))
    try:
        assert _check_tool_authz("create_workspace", {}) is None
        assert _check_tool_authz("create_document", {"workspace_slug": _WS}) is None
    finally:
        reset_current_session(token)  # type: ignore[arg-type]


def test_cle_scopee_lecture_seule() -> None:
    session, token = _use_session(
        McpSession(user=_user(), api_key_scopes=[_scope(_WS, read_only=True)])
    )
    try:
        # lecture dans le périmètre → OK
        assert _check_tool_authz("list_documents", {"workspace_slug": _WS}) is None
        assert _check_tool_authz("get_document", {"workspace_slug": _WS}) is None
        # écriture → refusée (read_only)
        denied = _check_tool_authz("create_document", {"workspace_slug": _WS})
        assert denied is not None
        assert "périmètre" in json.loads(denied[0].text)["error"]
        # hors workspace → refusé
        denied = _check_tool_authz("list_documents", {"workspace_slug": "autre-ws"})
        assert denied is not None
    finally:
        reset_current_session(token)  # type: ignore[arg-type]


def test_cle_scopee_ecriture_ws() -> None:
    session, token = _use_session(McpSession(user=_user(), api_key_scopes=[_scope(_WS)]))
    try:
        assert _check_tool_authz("create_document", {"workspace_slug": _WS}) is None
        assert _check_tool_authz("update_document", {"workspace_slug": _WS}) is None
        # outils structurels → toujours refusés aux clés non-admin
        for tool in (
            "create_workspace",
            "import_template",
            "create_api_profile",
            "generate_api_key",
        ):
            denied = _check_tool_authz(tool, {})
            assert denied is not None, tool
            assert "interdite" in json.loads(denied[0].text)["error"]
    finally:
        reset_current_session(token)  # type: ignore[arg-type]


def test_cle_scopee_niveau_bloc() -> None:
    """Un scope au niveau bloc ne couvre que ce bloc (miroir de check_api_key_scope)."""
    session, token = _use_session(
        McpSession(user=_user(), api_key_scopes=[_scope(_WS, block="bloc-a")])
    )
    try:
        assert (
            _check_tool_authz("create_document", {"workspace_slug": _WS, "block_slug": "bloc-a"})
            is None
        )
        denied = _check_tool_authz(
            "create_document", {"workspace_slug": _WS, "block_slug": "bloc-b"}
        )
        assert denied is not None
        # outil sans block_slug (périmètre ws entier) → refusé pour un scope bloc
        denied = _check_tool_authz("list_documents", {"workspace_slug": _WS})
        assert denied is not None
    finally:
        reset_current_session(token)  # type: ignore[arg-type]


# ── Intégration _call_tool (DB) ───────────────────────────────────────────────


async def test_call_tool_refuse_hors_scope(db_pool: asyncpg.Pool, test_workspace: dict) -> None:
    configure(db_pool)
    session, token = _use_session(
        McpSession(user=_user(), api_key_scopes=[_scope("autre-ws", read_only=True)])
    )
    try:
        result = await _call_tool("list_documents", {"workspace_slug": _WS})
        # Refus d'autorisation = échec → isError (jamais ok:true/200).
        assert result.isError is True
        payload = json.loads(result.content[0].text)
        assert "périmètre" in payload["error"]
    finally:
        reset_current_session(token)  # type: ignore[arg-type]


async def test_list_workspaces_filtre_par_scope(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    configure(db_pool)
    session, token = _use_session(
        McpSession(user=_user(), api_key_scopes=[_scope("un-autre-ws", read_only=True)])
    )
    try:
        result = await _call_tool("list_workspaces", {})
        assert json.loads(result[0].text) == []
    finally:
        reset_current_session(token)  # type: ignore[arg-type]


async def test_list_workspaces_complet_en_jwt(
    db_pool: asyncpg.Pool, test_workspace: dict, jwt_session: McpSession
) -> None:
    """Session JWT non scopée par clé : list_workspaces retourne les workspaces
    accessibles à l'utilisateur du JWT (design : le JWT est soumis à l'accès-
    utilisateur). L'utilisateur possède ici test-ws → il le voit."""
    configure(db_pool)
    # L'utilisateur du JWT devient owner du workspace de test → accès garanti.
    await db_pool.execute(
        "INSERT INTO app_user (id, email, label, validated) VALUES ($1, $2, $3, true) "
        "ON CONFLICT (id) DO NOTHING",
        jwt_session.user.id,
        jwt_session.user.email,
        jwt_session.user.label,
    )
    await db_pool.execute(
        "UPDATE workspace SET owner_id = $1 WHERE slug = $2",
        jwt_session.user.id,
        _WS,
    )
    result = await _call_tool("list_workspaces", {})
    slugs = {w["slug"] for w in json.loads(result[0].text)}
    assert _WS in slugs


# ── Montage des endpoints ASGI purs ───────────────────────────────────────────


def test_mcp_endpoints_montes_et_proteges(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les routes MCP (ASGI pur, hors OpenAPI) sont montées et exigent l'auth.

    Régression : elles ne doivent JAMAIS redevenir des routes FastAPI
    classiques — le transport SSE répond lui-même sur le cycle ASGI, une
    réponse FastAPI supplémentaire casse le keep-alive des clients MCP
    (second http.response.start).
    """
    from fastapi.testclient import TestClient

    from docflow.app import app

    monkeypatch.setenv("DATABASE_URL", "postgresql://invalide/x")
    monkeypatch.setenv("JWT_SECRET", "s" * 64)
    client = TestClient(app)  # sans lifespan : pas de DB requise pour le 401
    r_sse = client.get("/api/mcp/sse")
    r_msg = client.post("/api/mcp/messages?session_id=deadbeef")
    assert (r_sse.status_code, r_sse.json()["detail"]) == (401, "token manquant")
    assert (r_msg.status_code, r_msg.json()["detail"]) == (401, "token manquant")

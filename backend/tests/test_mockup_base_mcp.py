"""Surface MCP mockup-base : set → apply → drift → propagate via les handlers."""

from __future__ import annotations

import json
import uuid

import asyncpg

from docflow.artifacts import service as art_svc
from docflow.config.settings import Settings
from docflow.mcp import artifact_tools
from docflow.mcp.session import McpSession, reset_current_session, set_current_session
from docflow.schemas.auth import AuthUser

_WS = "test-ws"


def _settings() -> Settings:
    return Settings(
        database_url="postgresql://x/y", jwt_secret="x" * 32, artifact_max_bytes=1_000_000
    )


async def _seed_user(pool: asyncpg.Pool) -> AuthUser:
    uid = await pool.fetchval(
        "INSERT INTO app_user (email, label, is_admin, validated) "
        "VALUES ($1, $2, true, true) RETURNING id",
        f"mockup-{uuid.uuid4().hex}@t.c",
        "Mockup Tester",
    )
    return AuthUser(id=uid, email="a@b.c", label="A", is_admin=True, validated=True, disabled=False)


def _payload(res: list) -> dict:
    return json.loads(res[0].text)


def test_registered_and_permissions() -> None:
    names = {t.name for t in artifact_tools.ARTIFACT_TOOLS}
    assert {
        "set_mockup_base",
        "apply_mockup_base",
        "propagate_mockup_base",
        "mockup_base_drift",
    } <= names
    ws = artifact_tools.ARTIFACT_WS_TOOLS
    assert ws["set_mockup_base"] and ws["apply_mockup_base"] and ws["propagate_mockup_base"]
    assert ws["mockup_base_drift"] is False  # lecture seule


async def test_mcp_cycle_set_apply_drift_propagate(
    db_pool: asyncpg.Pool, test_workspace: dict
) -> None:
    token = set_current_session(McpSession(user=await _seed_user(db_pool)))
    try:
        await _run_cycle(db_pool)
    finally:
        reset_current_session(token)


async def _run_cycle(db_pool: asyncpg.Pool) -> None:
    s = _settings()
    # set (création)
    created = _payload(
        await artifact_tools.handle_set_mockup_base(
            db_pool, s, {"workspace_slug": _WS, "css": ":root{--c:#111}"}
        )
    )
    base_id = created["base_id"]
    assert created["revision"] == 1

    # maquette + apply
    maq = await art_svc.create_artifact(
        db_pool,
        _WS,
        filename="m.html",
        data=b"<head></head><body>x</body>",
        created_by=None,
        max_bytes=1_000_000,
        mutable=True,
    )
    applied = _payload(
        await artifact_tools.handle_apply_mockup_base(
            db_pool, s, {"workspace_slug": _WS, "base_id": base_id, "maquette_id": str(maq.id)}
        )
    )
    assert applied["changed"] is True and applied["base_rev"] == 1

    # bump base + propagate
    _payload(
        await artifact_tools.handle_set_mockup_base(
            db_pool,
            s,
            {"workspace_slug": _WS, "css": ":root{--c:#222}", "base_id": base_id, "if_revision": 1},
        )
    )
    prop = _payload(
        await artifact_tools.handle_propagate_mockup_base(
            db_pool, s, {"workspace_slug": _WS, "base_id": base_id}
        )
    )
    assert len(prop["updated"]) == 1 and prop["current_rev"] == 2

    # drift : tout à jour
    drift = _payload(
        await artifact_tools.handle_mockup_base_drift(
            db_pool, {"workspace_slug": _WS, "base_id": base_id}
        )
    )
    assert drift["stale"] == 0 and drift["total"] == 1


async def test_mcp_bad_uuid_is_clean_error(db_pool: asyncpg.Pool) -> None:
    token = set_current_session(McpSession(user=await _seed_user(db_pool)))
    try:
        res = _payload(
            await artifact_tools.handle_apply_mockup_base(
                db_pool,
                _settings(),
                {"workspace_slug": _WS, "base_id": "nope", "maquette_id": "nope"},
            )
        )
        assert "error" in res
    finally:
        reset_current_session(token)

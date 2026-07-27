"""Contrôle d'accès par utilisateur sur la surface MCP (accès workspace).

Design : accès au niveau workspace — superadmin OU owner OU membre. Les objets
internes héritent de l'accès du workspace. Une session clé API doit satisfaire
le scope de clé ET l'accès-utilisateur ; superadmin bypass.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

import asyncpg
import pytest

from docflow.mcp.server import (
    _call_tool,
    _list_workspaces,
    configure,
)
from docflow.mcp.session import McpSession, reset_current_session, set_current_session
from docflow.schemas.auth import AuthUser
from docflow.workspaces.access import accessible_workspace_slugs, user_can_access_workspace


def _json(result: list) -> object:
    return json.loads(result[0].text)


async def _make_user(pool: asyncpg.Pool, email: str, *, is_admin: bool = False) -> AuthUser:
    row = await pool.fetchrow(
        "INSERT INTO app_user (email, label, is_admin, validated) VALUES ($1, $2, $3, true) "
        "ON CONFLICT (email) DO UPDATE SET is_admin = EXCLUDED.is_admin RETURNING id",
        email,
        email,
        is_admin,
    )
    assert row is not None
    return AuthUser(
        id=row["id"],
        email=email,
        label=email,
        is_admin=is_admin,
        validated=True,
        disabled=False,
    )


@contextmanager
def _session(user: AuthUser) -> Iterator[None]:
    token = set_current_session(McpSession(user=user))
    try:
        yield
    finally:
        reset_current_session(token)


@pytest.fixture()
async def acc(db_pool: asyncpg.Pool) -> AsyncIterator[dict[str, object]]:
    """Utilisateurs (owner/member/other/admin) + un workspace possédé par owner."""
    configure(db_pool)
    await db_pool.execute("DELETE FROM workspace WHERE slug LIKE 'acc-%'")
    await db_pool.execute("DELETE FROM app_user WHERE email LIKE 'acc-%@test.local'")

    owner = await _make_user(db_pool, "acc-owner@test.local")
    member = await _make_user(db_pool, "acc-member@test.local")
    other = await _make_user(db_pool, "acc-other@test.local")
    admin = await _make_user(db_pool, "acc-admin@test.local", is_admin=True)

    wk: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO workspace (slug, label, owner_id) VALUES ($1, $2, $3) "
        "RETURNING workspace_technical_key",
        "acc-ws",
        "Access WS",
        owner.id,
    )
    await db_pool.execute(
        "INSERT INTO functional_type (slug, label, workspace_technical_key) VALUES ($1, $2, $3)",
        "epic",
        "Epic",
        wk,
    )
    try:
        yield {
            "owner": owner,
            "member": member,
            "other": other,
            "admin": admin,
            "ws_slug": "acc-ws",
            "wk": wk,
        }
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug LIKE 'acc-%'")
        await db_pool.execute("DELETE FROM app_user WHERE email LIKE 'acc-%@test.local'")


# ---------------------------------------------------------------------------
# user_can_access_workspace (unitaire)
# ---------------------------------------------------------------------------


async def test_can_access_owner(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    async with db_pool.acquire() as conn:
        assert await user_can_access_workspace(conn, acc["wk"], acc["owner"]) is True


async def test_can_access_member(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    await db_pool.execute(
        "INSERT INTO workspace_member (workspace_technical_key, user_id) VALUES ($1, $2)",
        acc["wk"],
        acc["member"].id,  # type: ignore[attr-defined]
    )
    async with db_pool.acquire() as conn:
        assert await user_can_access_workspace(conn, acc["wk"], acc["member"]) is True


async def test_can_access_superadmin(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    async with db_pool.acquire() as conn:
        assert await user_can_access_workspace(conn, acc["wk"], acc["admin"]) is True


async def test_can_access_tiers_false(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    async with db_pool.acquire() as conn:
        assert await user_can_access_workspace(conn, acc["wk"], acc["other"]) is False


async def test_can_access_owner_null_non_admin_false(db_pool: asyncpg.Pool) -> None:
    """Owner NULL, sans membre, non-admin ⇒ refus (fail-safe)."""
    user = await _make_user(db_pool, "acc-nul@test.local")
    wk: uuid.UUID = await db_pool.fetchval(
        "INSERT INTO workspace (slug, label) VALUES ($1, $2) RETURNING workspace_technical_key",
        "acc-null-ws",
        "Null WS",
    )
    try:
        async with db_pool.acquire() as conn:
            assert await user_can_access_workspace(conn, wk, user) is False
    finally:
        await db_pool.execute("DELETE FROM workspace WHERE slug = 'acc-null-ws'")
        await db_pool.execute("DELETE FROM app_user WHERE email = 'acc-nul@test.local'")


# ---------------------------------------------------------------------------
# Enforcement via _call_tool
# ---------------------------------------------------------------------------


async def test_enforcement_owner_passe(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    with _session(acc["owner"]):  # type: ignore[arg-type]
        data = _json(await _call_tool("list_types", {"workspace_slug": "acc-ws"}))
    assert isinstance(data, list)


async def test_enforcement_tiers_refuse(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    with _session(acc["other"]):  # type: ignore[arg-type]
        data = _json(await _call_tool("list_types", {"workspace_slug": "acc-ws"}))
    assert isinstance(data, dict)
    assert "accès refusé" in data["error"]  # type: ignore[index]


async def test_enforcement_superadmin_passe(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    with _session(acc["admin"]):  # type: ignore[arg-type]
        data = _json(await _call_tool("list_types", {"workspace_slug": "acc-ws"}))
    assert isinstance(data, list)


async def test_enforcement_membre_passe(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    await db_pool.execute(
        "INSERT INTO workspace_member (workspace_technical_key, user_id) VALUES ($1, $2)",
        acc["wk"],
        acc["member"].id,  # type: ignore[attr-defined]
    )
    with _session(acc["member"]):  # type: ignore[arg-type]
        data = _json(await _call_tool("list_types", {"workspace_slug": "acc-ws"}))
    assert isinstance(data, list)


async def test_enforcement_workspace_inconnu_laisse_handler(
    db_pool: asyncpg.Pool, acc: dict[str, object]
) -> None:
    """Workspace inexistant : l'enforcement n'intercepte pas (pas de faux « accès
    refusé »), le handler traite le workspace absent comme d'habitude."""
    with _session(acc["other"]), pytest.raises(ValueError, match="introuvable"):
        await _call_tool("list_types", {"workspace_slug": "acc-inexistant"})


# ---------------------------------------------------------------------------
# _list_workspaces : filtrage par accès-utilisateur
# ---------------------------------------------------------------------------


async def test_list_workspaces_non_admin_filtre(
    db_pool: asyncpg.Pool, acc: dict[str, object]
) -> None:
    # Un workspace étranger (owner = other) ne doit pas apparaître pour owner.
    await db_pool.execute(
        "INSERT INTO workspace (slug, label, owner_id) VALUES ($1, $2, $3)",
        "acc-ws-foreign",
        "Foreign",
        acc["other"].id,  # type: ignore[attr-defined]
    )
    with _session(acc["owner"]):  # type: ignore[arg-type]
        data = _json(await _list_workspaces(db_pool))
    slugs = {w["slug"] for w in data}  # type: ignore[union-attr]
    assert "acc-ws" in slugs
    assert "acc-ws-foreign" not in slugs


async def test_list_workspaces_superadmin_voit_tout(
    db_pool: asyncpg.Pool, acc: dict[str, object]
) -> None:
    await db_pool.execute(
        "INSERT INTO workspace (slug, label, owner_id) VALUES ($1, $2, $3)",
        "acc-ws-foreign",
        "Foreign",
        acc["other"].id,  # type: ignore[attr-defined]
    )
    with _session(acc["admin"]):  # type: ignore[arg-type]
        data = _json(await _list_workspaces(db_pool))
    slugs = {w["slug"] for w in data}  # type: ignore[union-attr]
    assert {"acc-ws", "acc-ws-foreign"} <= slugs


async def test_accessible_slugs_superadmin_none(
    db_pool: asyncpg.Pool, acc: dict[str, object]
) -> None:
    assert await accessible_workspace_slugs(db_pool, acc["admin"]) is None  # type: ignore[arg-type]


async def test_accessible_slugs_membre(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    await db_pool.execute(
        "INSERT INTO workspace_member (workspace_technical_key, user_id) VALUES ($1, $2)",
        acc["wk"],
        acc["member"].id,  # type: ignore[attr-defined]
    )
    slugs = await accessible_workspace_slugs(db_pool, acc["member"])  # type: ignore[arg-type]
    assert slugs == {"acc-ws"}


# ---------------------------------------------------------------------------
# Gestion des membres
# ---------------------------------------------------------------------------


async def test_owner_ajoute_membre_qui_accede(
    db_pool: asyncpg.Pool, acc: dict[str, object]
) -> None:
    # L'owner ajoute member.
    with _session(acc["owner"]):  # type: ignore[arg-type]
        added = _json(
            await _call_tool(
                "add_workspace_member",
                {"workspace_slug": "acc-ws", "member_email": "acc-member@test.local"},
            )
        )
    assert added["added"] is True  # type: ignore[index]

    # member accède désormais.
    with _session(acc["member"]):  # type: ignore[arg-type]
        data = _json(await _call_tool("list_types", {"workspace_slug": "acc-ws"}))
    assert isinstance(data, list)

    # Retrait → n'accède plus.
    with _session(acc["owner"]):  # type: ignore[arg-type]
        removed = _json(
            await _call_tool(
                "remove_workspace_member",
                {"workspace_slug": "acc-ws", "member_email": "acc-member@test.local"},
            )
        )
    assert removed["removed"] is True  # type: ignore[index]

    with _session(acc["member"]):  # type: ignore[arg-type]
        denied = _json(await _call_tool("list_types", {"workspace_slug": "acc-ws"}))
    assert "accès refusé" in denied["error"]  # type: ignore[index]


async def test_list_members_expose_owner(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    with _session(acc["owner"]):  # type: ignore[arg-type]
        _json(
            await _call_tool(
                "add_workspace_member",
                {
                    "workspace_slug": "acc-ws",
                    "member_email": "acc-member@test.local",
                    "role": "member",
                },
            )
        )
        data = _json(await _call_tool("list_workspace_members", {"workspace_slug": "acc-ws"}))
    assert data["owner_email"] == "acc-owner@test.local"  # type: ignore[index]
    emails = {m["email"] for m in data["members"]}  # type: ignore[index]
    assert "acc-member@test.local" in emails


async def test_tiers_ne_peut_gerer_membres(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    """Un membre (non-owner, non-admin) ne peut pas gérer les membres."""
    await db_pool.execute(
        "INSERT INTO workspace_member (workspace_technical_key, user_id) VALUES ($1, $2)",
        acc["wk"],
        acc["member"].id,  # type: ignore[attr-defined]
    )
    # member a accès au workspace mais n'est pas owner → gestion refusée.
    with _session(acc["member"]):  # type: ignore[arg-type]
        data = _json(
            await _call_tool(
                "add_workspace_member",
                {"workspace_slug": "acc-ws", "member_email": "acc-other@test.local"},
            )
        )
    assert "error" in data  # type: ignore[operator]
    # other n'a toujours pas accès.
    with _session(acc["other"]):  # type: ignore[arg-type]
        denied = _json(await _call_tool("list_types", {"workspace_slug": "acc-ws"}))
    assert "accès refusé" in denied["error"]  # type: ignore[index]


async def test_add_member_non_valide_refuse(db_pool: asyncpg.Pool, acc: dict[str, object]) -> None:
    """Un utilisateur non validé ne peut pas être ajouté comme membre."""
    await db_pool.execute(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, false)",
        "acc-invalide@test.local",
        "Invalide",
    )
    try:
        with _session(acc["owner"]):  # type: ignore[arg-type]
            data = _json(
                await _call_tool(
                    "add_workspace_member",
                    {"workspace_slug": "acc-ws", "member_email": "acc-invalide@test.local"},
                )
            )
        assert "error" in data  # type: ignore[operator]
    finally:
        await db_pool.execute("DELETE FROM app_user WHERE email = 'acc-invalide@test.local'")

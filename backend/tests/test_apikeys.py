from __future__ import annotations

import uuid

import asyncpg
import pytest

from docflow.apikeys import service as svc
from docflow.apikeys.schemas import ApiKeyCreate, ApiProfileCreate, ApiProfileScopeIn


# ── Fixture : utilisateur propriétaire ───────────────────────────────────────

@pytest.fixture()
async def owner(db_pool: asyncpg.Pool) -> uuid.UUID:
    row = await db_pool.fetchrow(
        "INSERT INTO app_user (email, label, password_hash, is_admin, validated, source) "
        "VALUES ($1, $2, $3, true, true, 'local') RETURNING id",
        "apikey-owner@test.local",
        "API Key Owner",
        "x",
    )
    assert row is not None
    oid: uuid.UUID = row["id"]
    yield oid
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", oid)


# ── Profils ───────────────────────────────────────────────────────────────────

async def test_create_profile_nominal(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="mon-profil"))
    assert p.name == "mon-profil"
    assert p.is_admin is False
    assert p.scope_count == 0
    assert p.key_count == 0


async def test_create_profile_admin(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="admin-profil", is_admin=True))
    assert p.is_admin is True


async def test_create_profile_nom_duplique(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    await svc.create_profile(db_pool, owner, ApiProfileCreate(name="dup"))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.create_profile(db_pool, owner, ApiProfileCreate(name="dup"))
    assert exc.value.status_code == 409


async def test_list_profiles(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    await svc.create_profile(db_pool, owner, ApiProfileCreate(name="p1"))
    await svc.create_profile(db_pool, owner, ApiProfileCreate(name="p2"))
    profiles = await svc.list_profiles(db_pool, owner)
    names = [p.name for p in profiles]
    assert "p1" in names
    assert "p2" in names


async def test_get_profile_detail(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="detail-test"))
    detail = await svc.get_profile(db_pool, owner, p.id)
    assert detail.id == p.id
    assert detail.scopes == []


async def test_get_profile_autre_owner_404(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="secret"))
    from fastapi import HTTPException
    autre = uuid.uuid4()
    with pytest.raises(HTTPException) as exc:
        await svc.get_profile(db_pool, autre, p.id)
    assert exc.value.status_code == 404


async def test_delete_profile(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="a-supprimer"))
    await svc.delete_profile(db_pool, owner, p.id)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.get_profile(db_pool, owner, p.id)
    assert exc.value.status_code == 404


async def test_delete_profile_autre_owner_404(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="intouchable"))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.delete_profile(db_pool, uuid.uuid4(), p.id)
    assert exc.value.status_code == 404


# ── Scopes ────────────────────────────────────────────────────────────────────

async def test_set_scopes_nominal(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="scoped"))
    scopes_in = [
        ApiProfileScopeIn(workspace_slug="ws-a", block_slug=None, read_only=True),
        ApiProfileScopeIn(workspace_slug="ws-b", block_slug="bloc-x", read_only=False),
    ]
    result = await svc.set_scopes(db_pool, owner, p.id, scopes_in)
    assert len(result) == 2
    ws_slugs = {s.workspace_slug for s in result}
    assert ws_slugs == {"ws-a", "ws-b"}


async def test_set_scopes_remplacement_atomique(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="replace-test"))
    await svc.set_scopes(db_pool, owner, p.id, [
        ApiProfileScopeIn(workspace_slug="old", block_slug=None, read_only=True),
    ])
    await svc.set_scopes(db_pool, owner, p.id, [
        ApiProfileScopeIn(workspace_slug="new", block_slug=None, read_only=False),
    ])
    detail = await svc.get_profile(db_pool, owner, p.id)
    assert len(detail.scopes) == 1
    assert detail.scopes[0].workspace_slug == "new"


async def test_set_scopes_dupliques_rejetes(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="dup-scope"))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.set_scopes(db_pool, owner, p.id, [
            ApiProfileScopeIn(workspace_slug="ws", block_slug=None, read_only=True),
            ApiProfileScopeIn(workspace_slug="ws", block_slug=None, read_only=False),
        ])
    assert exc.value.status_code == 422


# ── Clés ─────────────────────────────────────────────────────────────────────

async def test_generate_key_nominal(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="keygen"))
    created = await svc.generate_key(db_pool, owner, ApiKeyCreate(profile_id=p.id, label="ci"))
    assert created.key.startswith("dfk_")
    assert len(created.key) > 20
    assert created.key_prefix == created.key[:12]
    assert created.revoked is False


async def test_generate_key_profil_autre_owner_404(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="foreign"))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.generate_key(db_pool, uuid.uuid4(), ApiKeyCreate(profile_id=p.id, label="x"))
    assert exc.value.status_code == 404


async def test_list_keys(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="listkeys"))
    await svc.generate_key(db_pool, owner, ApiKeyCreate(profile_id=p.id, label="k1"))
    await svc.generate_key(db_pool, owner, ApiKeyCreate(profile_id=p.id, label="k2"))
    keys = await svc.list_keys(db_pool, owner)
    labels = [k.label for k in keys]
    assert "k1" in labels
    assert "k2" in labels


async def test_revoke_key(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="revoke-test"))
    created = await svc.generate_key(db_pool, owner, ApiKeyCreate(profile_id=p.id, label="r"))
    await svc.revoke_key(db_pool, owner, created.id)
    keys = await svc.list_keys(db_pool, owner)
    revoked = next(k for k in keys if k.id == created.id)
    assert revoked.revoked is True


async def test_revoke_key_deja_revoquee(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="double-revoke"))
    created = await svc.generate_key(db_pool, owner, ApiKeyCreate(profile_id=p.id, label="x"))
    await svc.revoke_key(db_pool, owner, created.id)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.revoke_key(db_pool, owner, created.id)
    assert exc.value.status_code == 404


# ── Résolution de clé ─────────────────────────────────────────────────────────

async def test_resolve_api_key_nominal(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="resolve"))
    await svc.set_scopes(db_pool, owner, p.id, [
        ApiProfileScopeIn(workspace_slug="ws-test", block_slug=None, read_only=True),
    ])
    created = await svc.generate_key(db_pool, owner, ApiKeyCreate(profile_id=p.id, label="res"))
    user, scopes, is_admin = await svc.resolve_api_key(db_pool, created.key)
    assert user.id == owner
    assert len(scopes) == 1
    assert scopes[0].workspace_slug == "ws-test"
    assert is_admin is False


async def test_resolve_api_key_admin_profile(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="resolve-admin", is_admin=True))
    created = await svc.generate_key(db_pool, owner, ApiKeyCreate(profile_id=p.id, label="adm"))
    _, scopes, is_admin = await svc.resolve_api_key(db_pool, created.key)
    assert is_admin is True
    assert scopes == []


async def test_resolve_api_key_invalide(db_pool: asyncpg.Pool) -> None:
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.resolve_api_key(db_pool, "dfk_CLEF_INEXISTANTE")
    assert exc.value.status_code == 401


async def test_resolve_api_key_revoquee(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="revoked-resolve"))
    created = await svc.generate_key(db_pool, owner, ApiKeyCreate(profile_id=p.id, label="rev"))
    await svc.revoke_key(db_pool, owner, created.id)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.resolve_api_key(db_pool, created.key)
    assert exc.value.status_code == 401


async def test_resolve_api_key_met_a_jour_last_used(db_pool: asyncpg.Pool, owner: uuid.UUID) -> None:
    p = await svc.create_profile(db_pool, owner, ApiProfileCreate(name="last-used"))
    created = await svc.generate_key(db_pool, owner, ApiKeyCreate(profile_id=p.id, label="lu"))
    last_used_before = await db_pool.fetchval(
        "SELECT last_used_at FROM api_key WHERE id = $1", created.id
    )
    assert last_used_before is None
    await svc.resolve_api_key(db_pool, created.key)
    last_used_after = await db_pool.fetchval(
        "SELECT last_used_at FROM api_key WHERE id = $1", created.id
    )
    assert last_used_after is not None

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.admin.users import service as svc
from docflow.schemas.admin_user import AdminUserCreate, AdminUserUpdate


# ── Helper ────────────────────────────────────────────────────────────────────

def _create(email: str, *, is_admin: bool = False, password: str = "s3cr3t") -> AdminUserCreate:
    return AdminUserCreate(email=email, label=email.split("@")[0], password=password, is_admin=is_admin)


# ── CRUD basique ──────────────────────────────────────────────────────────────

async def test_create_user_nominal(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    u = await svc.create_user(db_pool, _create("alice@test.local"))
    assert u.email == "alice@test.local"
    assert u.is_admin is False
    assert u.validated is True  # l'admin crée des comptes immédiatement validés
    assert u.has_local_password is True
    assert u.source == "local"


async def test_create_user_admin(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    u = await svc.create_user(db_pool, _create("admin@test.local", is_admin=True))
    assert u.is_admin is True


async def test_create_user_email_duplique(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    await svc.create_user(db_pool, _create("dup@test.local"))
    with pytest.raises(HTTPException) as exc:
        await svc.create_user(db_pool, _create("dup@test.local"))
    assert exc.value.status_code == 409


async def test_get_user(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    u = await svc.create_user(db_pool, _create("get@test.local"))
    fetched = await svc.get_user(db_pool, u.id)
    assert fetched.id == u.id
    assert fetched.email == "get@test.local"


async def test_get_user_introuvable(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await svc.get_user(db_pool, uuid.uuid4())
    assert exc.value.status_code == 404


async def test_list_users(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    await svc.create_user(db_pool, _create("u1@test.local"))
    await svc.create_user(db_pool, _create("u2@test.local"))
    users = await svc.list_users(db_pool)
    emails = [u.email for u in users]
    assert "u1@test.local" in emails
    assert "u2@test.local" in emails


async def test_update_user_label(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    u = await svc.create_user(db_pool, _create("upd@test.local"))
    updated = await svc.update_user(db_pool, u.id, AdminUserUpdate(label="Nouveau Label"))
    assert updated.label == "Nouveau Label"


async def test_update_user_email_duplique(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    await svc.create_user(db_pool, _create("existing@test.local"))
    u2 = await svc.create_user(db_pool, _create("other@test.local"))
    with pytest.raises(HTTPException) as exc:
        await svc.update_user(db_pool, u2.id, AdminUserUpdate(email="existing@test.local"))
    assert exc.value.status_code == 409


async def test_delete_user(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    # Créer deux admins pour que la suppression soit autorisée
    u1 = await svc.create_user(db_pool, _create("del1@test.local", is_admin=True))
    await svc.create_user(db_pool, _create("del2@test.local", is_admin=True))
    await svc.delete_user(db_pool, u1.id)
    with pytest.raises(HTTPException) as exc:
        await svc.get_user(db_pool, u1.id)
    assert exc.value.status_code == 404


async def test_delete_user_introuvable(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await svc.delete_user(db_pool, uuid.uuid4())
    assert exc.value.status_code == 404


# ── Validation ────────────────────────────────────────────────────────────────

async def test_validate_user(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    u = await svc.create_user(db_pool, _create("v@test.local"))
    assert u.validated is True  # créé validé par l'admin
    # Dés-validation puis re-validation
    unv = await svc.validate_user(db_pool, u.id, validated=False)
    assert unv.validated is False
    rev = await svc.validate_user(db_pool, u.id, validated=True)
    assert rev.validated is True


async def test_unvalidate_user(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    u = await svc.create_user(db_pool, _create("unv@test.local"))
    await svc.validate_user(db_pool, u.id, validated=True)
    unvalidated = await svc.validate_user(db_pool, u.id, validated=False)
    assert unvalidated.validated is False


async def test_validate_user_introuvable(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await svc.validate_user(db_pool, uuid.uuid4(), validated=True)
    assert exc.value.status_code == 404


# ── Mot de passe ──────────────────────────────────────────────────────────────

async def test_set_password(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    u = await svc.create_user(db_pool, _create("pwd@test.local"))
    updated = await svc.set_password(db_pool, u.id, "nouveau-mdp-fort")
    assert updated.has_local_password is True


async def test_set_password_introuvable(db_pool: asyncpg.Pool) -> None:
    with pytest.raises(HTTPException) as exc:
        await svc.set_password(db_pool, uuid.uuid4(), "x")
    assert exc.value.status_code == 404


# ── Garde-fou anti-lock-out ───────────────────────────────────────────────────

async def test_anti_lockout_disable_dernier_admin(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    """Désactiver le dernier admin local connectable doit être refusé (422)."""
    admin = await svc.create_user(db_pool, _create("last-admin@test.local", is_admin=True))
    with pytest.raises(HTTPException) as exc:
        await svc.update_user(db_pool, admin.id, AdminUserUpdate(disabled=True))
    assert exc.value.status_code == 422
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "last_local_admin"


async def test_anti_lockout_delete_dernier_admin(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    """Supprimer le dernier admin local connectable doit être refusé (422)."""
    admin = await svc.create_user(db_pool, _create("last-del@test.local", is_admin=True))
    with pytest.raises(HTTPException) as exc:
        await svc.delete_user(db_pool, admin.id)
    assert exc.value.status_code == 422


async def test_anti_lockout_ok_si_autre_admin(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    """Supprimer un admin est autorisé s'il en reste un autre."""
    a1 = await svc.create_user(db_pool, _create("adm-a@test.local", is_admin=True))
    await svc.create_user(db_pool, _create("adm-b@test.local", is_admin=True))
    await svc.delete_user(db_pool, a1.id)  # ne doit pas lever d'exception


async def test_anti_lockout_ok_si_admin_non_local(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    """Un admin OIDC (sans password_hash) ne compte pas comme admin local connectable."""
    local_admin = await svc.create_user(db_pool, _create("local@test.local", is_admin=True))
    # Insérer un admin OIDC sans password_hash
    await db_pool.execute(
        "INSERT INTO app_user (email, label, password_hash, is_admin, validated, disabled, source) "
        "VALUES ($1, $2, NULL, true, true, false, 'oidc')",
        "oidc-admin@test.local",
        "OIDC Admin",
    )
    # Supprimer le local : toujours refusé car l'OIDC ne compte pas
    with pytest.raises(HTTPException) as exc:
        await svc.delete_user(db_pool, local_admin.id)
    assert exc.value.status_code == 422

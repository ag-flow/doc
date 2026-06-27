from __future__ import annotations

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.oidc import service as oidc_svc
from docflow.schemas.oidc import OidcConfigSet

_VAULT_REF = "${vault://harpocrate:/docflow/oidc_secret}"
_SECRET_REF = "inline-secret-value"


async def test_set_and_get_oidc_config(db_pool: asyncpg.Pool) -> None:
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://security.yoops.org/realms/yoops",
            client_id="docflow",
            client_secret_ref=_VAULT_REF,
            enabled=False,
        ),
    )
    config = await oidc_svc.get_oidc_config(db_pool)
    assert config is not None
    assert config.issuer == "https://security.yoops.org/realms/yoops"
    assert config.client_id == "docflow"
    assert config.enabled is False
    # I-8 : le client_secret_ref ne doit pas apparaître dans la réponse API
    config_dict = config.model_dump()
    assert "client_secret_ref" not in config_dict


async def test_secret_not_in_response_i8(db_pool: asyncpg.Pool) -> None:
    """I-8 : OidcConfigOut ne contient pas client_secret_ref."""
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://issuer.example.com",
            client_id="my-client",
            client_secret_ref=_VAULT_REF,
            enabled=True,
        ),
    )
    out = await oidc_svc.get_oidc_config(db_pool)
    assert out is not None
    # La valeur du vault ref ne doit pas fuiter
    out_json = out.model_dump_json()
    assert _VAULT_REF not in out_json
    assert "vault://" not in out_json


async def test_upsert_oidc_config(db_pool: asyncpg.Pool) -> None:
    """PUT deux fois → une seule ligne."""
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://a.example.com",
            client_id="client-a",
            client_secret_ref=_SECRET_REF,
            enabled=False,
        ),
    )
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://b.example.com",
            client_id="client-b",
            client_secret_ref=_SECRET_REF,
            enabled=True,
        ),
    )
    config = await oidc_svc.get_oidc_config(db_pool)
    assert config is not None
    assert config.issuer == "https://b.example.com"
    assert config.enabled is True
    count: int = await db_pool.fetchval("SELECT count(*) FROM oidc_config")
    assert count == 1


async def test_oidc_callback_rejected_when_disabled(db_pool: asyncpg.Pool) -> None:
    """Callback OIDC rejeté si enabled=false."""
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://issuer.example.com",
            client_id="c",
            client_secret_ref=_SECRET_REF,
            enabled=False,
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await oidc_svc.handle_oidc_callback(
            db_pool, "jwt-secret",
            {"email": "user@example.com", "sub": "keycloak-sub-1"},
        )
    assert exc.value.status_code == 403


async def test_oidc_provisioning_new_user(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    """Callback OIDC avec email inconnu → provisionnement sans password_hash."""
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://issuer.example.com",
            client_id="c",
            client_secret_ref=_SECRET_REF,
            enabled=True,
        ),
    )
    token = await oidc_svc.handle_oidc_callback(
        db_pool, "test-secret-key-for-unit-tests-hs256",
        {"email": "oidc-user@example.com", "sub": "sub-new-user", "name": "OIDC User"},
    )
    assert isinstance(token, str)
    pw_hash: str | None = await db_pool.fetchval(
        "SELECT password_hash FROM admin_user WHERE email = $1", "oidc-user@example.com"
    )
    assert pw_hash is None


async def test_oidc_link_existing_user_preserves_password(
    db_pool: asyncpg.Pool, clean_admin_users: None
) -> None:
    """1er login fédéré d'un admin local → oidc_subject rempli, password_hash préservé."""
    # Créer admin local
    from docflow.auth.password import hash_password
    await db_pool.execute(
        "INSERT INTO admin_user (email, label, password_hash, is_superadmin) "
        "VALUES ($1, $2, $3, false)",
        "existing@example.com", "Existing", hash_password("secret"),
    )
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://issuer.example.com",
            client_id="c",
            client_secret_ref=_SECRET_REF,
            enabled=True,
        ),
    )
    await oidc_svc.handle_oidc_callback(
        db_pool, "test-secret-key-for-unit-tests-hs256",
        {"email": "existing@example.com", "sub": "keycloak-sub-existing"},
    )
    row = await db_pool.fetchrow(
        "SELECT password_hash, oidc_subject FROM admin_user WHERE email = $1",
        "existing@example.com",
    )
    assert row is not None
    assert row["password_hash"] is not None
    assert row["oidc_subject"] == "keycloak-sub-existing"


async def test_public_config_hidden_when_disabled(db_pool: asyncpg.Pool) -> None:
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://issuer.example.com",
            client_id="c",
            client_secret_ref=_SECRET_REF,
            enabled=False,
        ),
    )
    public = await oidc_svc.get_public_config(db_pool)
    assert public is None

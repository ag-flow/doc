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
        await oidc_svc.provision_user_for_verified_claims(
        db_pool,
            {"email": "user@example.com", "sub": "keycloak-sub-1"},
            issuer="https://issuer.example.com",
        )
    assert exc.value.status_code == 403


async def test_oidc_provisioning_new_user(db_pool: asyncpg.Pool, clean_admin_users: None) -> None:
    """Callback OIDC avec email inconnu → provisionnement sans password_hash, mais
    compte non validé (0027_user_model) : rejet 403 PendingValidation tant qu'un
    admin ne l'a pas validé — pas de token à la première fédération."""
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://issuer.example.com",
            client_id="c",
            client_secret_ref=_SECRET_REF,
            enabled=True,
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await oidc_svc.provision_user_for_verified_claims(
        db_pool,
            {"email": "oidc-user@example.com", "sub": "sub-new-user", "name": "OIDC User"},
            issuer="https://issuer.example.com",
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "PendingValidation"

    row = await db_pool.fetchrow(
        "SELECT password_hash, validated FROM app_user WHERE email = $1",
        "oidc-user@example.com",
    )
    assert row is not None
    assert row["password_hash"] is None
    assert row["validated"] is False


async def test_oidc_link_existing_user_preserves_password(
    db_pool: asyncpg.Pool, clean_admin_users: None
) -> None:
    """1er login fédéré d'un admin local → oidc_subject rempli, password_hash préservé."""
    # Créer admin local
    from docflow.auth.password import hash_password

    await db_pool.execute(
        "INSERT INTO app_user (email, label, password_hash, is_admin, validated) "
        "VALUES ($1, $2, $3, false, true)",
        "existing@example.com",
        "Existing",
        hash_password("secret"),
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
    # email_verified=True requis pour lier un compte existant par email (AUTH-02)
    await oidc_svc.provision_user_for_verified_claims(
        db_pool,
        {"email": "existing@example.com", "sub": "keycloak-sub-existing", "email_verified": True},
        issuer="https://issuer.example.com",
    )
    row = await db_pool.fetchrow(
        "SELECT password_hash, oidc_subject FROM app_user WHERE email = $1",
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


async def test_login_config_includes_authorization_endpoint(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La mire de connexion a besoin de l'authorization_endpoint découvert."""
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://issuer.example.com",
            client_id="docflow",
            client_secret_ref=_SECRET_REF,
            enabled=True,
        ),
    )

    async def fake_discovery(issuer: str) -> dict[str, object]:
        return {
            "issuer": issuer,
            "authorization_endpoint": "https://issuer.example.com/protocol/openid-connect/auth",
        }

    monkeypatch.setattr(oidc_svc, "fetch_discovery", fake_discovery)
    public = await oidc_svc.get_login_config(db_pool)
    assert public is not None
    assert (
        public.authorization_endpoint == "https://issuer.example.com/protocol/openid-connect/auth"
    )


async def test_login_config_none_when_disabled(db_pool: asyncpg.Pool) -> None:
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://issuer.example.com",
            client_id="docflow",
            client_secret_ref=_SECRET_REF,
            enabled=False,
        ),
    )
    assert await oidc_svc.get_login_config(db_pool) is None


async def test_login_config_502_when_issuer_unreachable(
    db_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer="https://issuer.example.com",
            client_id="docflow",
            client_secret_ref=_SECRET_REF,
            enabled=True,
        ),
    )

    async def failing_discovery(issuer: str) -> dict[str, object]:
        raise oidc_svc.OidcVerifyError("injoignable")

    monkeypatch.setattr(oidc_svc, "fetch_discovery", failing_discovery)
    with pytest.raises(HTTPException) as exc_info:
        await oidc_svc.get_login_config(db_pool)
    assert exc_info.value.status_code == 502


# ── Ancrage sur le couple (issuer, sub) ─────────────────────────────────────

_ISS_A = "https://issuer-a.example.com"
_ISS_B = "https://issuer-b.example.com"


async def _enable_oidc(db_pool: asyncpg.Pool) -> None:
    await oidc_svc.set_oidc_config(
        db_pool,
        OidcConfigSet(
            issuer=_ISS_A, client_id="c", client_secret_ref=_SECRET_REF, enabled=True
        ),
    )


async def test_same_sub_two_issuers_are_two_accounts(
    db_pool: asyncpg.Pool, clean_admin_users: None
) -> None:
    """AC : deux `sub` identiques provenant de deux émetteurs distincts restent
    deux comptes distincts (l'ancrage est le COUPLE, pas le sub seul)."""
    await _enable_oidc(db_pool)
    for exc_email, issuer in (("a@example.com", _ISS_A), ("b@example.com", _ISS_B)):
        with pytest.raises(HTTPException) as exc:  # PendingValidation (nouveau compte)
            await oidc_svc.provision_user_for_verified_claims(
                db_pool,
                {"email": exc_email, "sub": "shared-sub", "email_verified": True},
                issuer=issuer,
            )
        assert exc.value.detail == "PendingValidation"
    rows = await db_pool.fetch(
        "SELECT oidc_issuer FROM app_user WHERE oidc_subject = 'shared-sub' ORDER BY oidc_issuer"
    )
    assert [r["oidc_issuer"] for r in rows] == [_ISS_A, _ISS_B]


async def _validated_pinned_account(db_pool: asyncpg.Pool, email: str) -> str:
    """Compte validé, épinglé (issuer A, sub 'sub-a') via le pont email vérifié."""
    await db_pool.execute(
        "INSERT INTO app_user (email, label, validated, source) VALUES ($1, $2, true, 'local')",
        email,
        "U",
    )
    user = await oidc_svc.provision_user_for_verified_claims(
        db_pool, {"email": email, "sub": "sub-a", "email_verified": True}, issuer=_ISS_A
    )
    return str(user.id)


async def test_relink_issuer_change_retrouve_le_compte(
    db_pool: asyncpg.Pool, clean_admin_users: None
) -> None:
    """AC : connu sous l'émetteur A, se connectant sous B avec le même email
    vérifié, retrouve son compte — re-liaison ouverte. Historique tenu."""
    await _enable_oidc(db_pool)
    uid = await _validated_pinned_account(db_pool, "switch@example.com")
    user = await oidc_svc.provision_user_for_verified_claims(
        db_pool,
        {"email": "switch@example.com", "sub": "sub-b", "email_verified": True},
        issuer=_ISS_B,
        relink_enabled=True,
    )
    assert str(user.id) == uid  # même compte
    row = await db_pool.fetchrow(
        "SELECT oidc_issuer, oidc_subject FROM app_user WHERE id = $1::uuid", uid
    )
    assert (row["oidc_issuer"], row["oidc_subject"]) == (_ISS_B, "sub-b")
    # Historique : ancien couple fermé, nouveau ouvert.
    hist = await db_pool.fetch(
        "SELECT issuer, unlinked_at FROM user_oidc_identity_history "
        "WHERE user_id = $1::uuid ORDER BY linked_at",
        uid,
    )
    assert [(h["issuer"], h["unlinked_at"] is None) for h in hist] == [
        (_ISS_A, False),
        (_ISS_B, True),
    ]


async def test_relink_ferme_par_defaut_refuse(
    db_pool: asyncpg.Pool, clean_admin_users: None
) -> None:
    """Fail closed : sans re-liaison ouverte, un changement d'émetteur est refusé."""
    await _enable_oidc(db_pool)
    await _validated_pinned_account(db_pool, "closed@example.com")
    with pytest.raises(HTTPException) as exc:
        await oidc_svc.provision_user_for_verified_claims(
            db_pool,
            {"email": "closed@example.com", "sub": "sub-b", "email_verified": True},
            issuer=_ISS_B,  # relink_enabled défaut False
        )
    assert exc.value.status_code == 401


async def test_meme_emetteur_sub_different_refuse_meme_relink_ouvert(
    db_pool: asyncpg.Pool, clean_admin_users: None
) -> None:
    """LE test à voir rouge si la garde est câblée sur le mode au lieu de
    l'émetteur : même émetteur, sub différent → refusé, y compris re-liaison ouverte."""
    await _enable_oidc(db_pool)
    await _validated_pinned_account(db_pool, "same@example.com")
    with pytest.raises(HTTPException) as exc:
        await oidc_svc.provision_user_for_verified_claims(
            db_pool,
            {"email": "same@example.com", "sub": "sub-autre", "email_verified": True},
            issuer=_ISS_A,  # MÊME émetteur, sub différent
            relink_enabled=True,  # ouvert : ne doit RIEN changer au refus
        )
    assert exc.value.status_code == 401

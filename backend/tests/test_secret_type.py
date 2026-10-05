"""T1 (E1) — Typage fonctionnel des secrets (`secret_type`).

Axe orthogonal à `kind` (politique de révélation) : `secret_type` classe le secret
par usage fonctionnel (liste extensible en MAJUSCULES). Introduit la valeur
`HARPOCRATE_API_KEY`, prérequis de l'endpoint vault propre (T2).
"""

from __future__ import annotations

import asyncpg
import pytest
from pydantic import ValidationError

from docflow.schemas.vault import VaultSecretCreate
from docflow.vault import service as vault_svc

_ENC_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


async def _owner(db_pool: asyncpg.Pool, email: str) -> asyncpg.Record:
    return await db_pool.fetchval(
        "INSERT INTO app_user (email, label, source, validated) "
        "VALUES ($1, 'T', 'local', true) RETURNING id",
        email,
    )


async def test_create_secret_defaults_to_generic_type(db_pool: asyncpg.Pool) -> None:
    """Sans type explicite, un secret est classé `GENERIC`."""
    owner = await _owner(db_pool, "stype-default@example.com")
    secret = await vault_svc.create_secret(
        db_pool, owner, VaultSecretCreate(label="Libre", slug="libre", value="x"),
        enc_key=_ENC_KEY,
    )
    assert secret.secret_type == "GENERIC"
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_create_secret_with_explicit_type(db_pool: asyncpg.Pool) -> None:
    """Un type explicite (ex. `HARPOCRATE_API_KEY`) est persisté et exposé."""
    owner = await _owner(db_pool, "stype-explicit@example.com")
    secret = await vault_svc.create_secret(
        db_pool,
        owner,
        VaultSecretCreate(
            label="Clé coffre", slug="cle-coffre", value="hrpv_1_abc",
            secret_type="HARPOCRATE_API_KEY",
        ),
        enc_key=_ENC_KEY,
    )
    assert secret.secret_type == "HARPOCRATE_API_KEY"
    listed = await vault_svc.list_secrets(db_pool, owner)
    assert next(s for s in listed if s.id == secret.id).secret_type == "HARPOCRATE_API_KEY"
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


async def test_list_secrets_filter_by_type(db_pool: asyncpg.Pool) -> None:
    """Le listing peut être restreint à un `secret_type`."""
    owner = await _owner(db_pool, "stype-filter@example.com")
    await vault_svc.create_secret(
        db_pool, owner, VaultSecretCreate(label="G", slug="g", value="x"), enc_key=_ENC_KEY,
    )
    key = await vault_svc.create_secret(
        db_pool,
        owner,
        VaultSecretCreate(
            label="K", slug="k", value="hrpv_1_z", secret_type="HARPOCRATE_API_KEY"
        ),
        enc_key=_ENC_KEY,
    )

    only_keys = await vault_svc.list_secrets(db_pool, owner, secret_type="HARPOCRATE_API_KEY")
    assert [s.id for s in only_keys] == [key.id]

    everything = await vault_svc.list_secrets(db_pool, owner)
    assert len(everything) == 2
    await db_pool.execute("DELETE FROM app_user WHERE id = $1", owner)


def test_secret_type_must_be_uppercase_slug() -> None:
    """Format de type imposé : MAJUSCULES, chiffres, underscore (liste extensible)."""
    with pytest.raises(ValidationError):
        VaultSecretCreate(label="X", slug="x", value="v", secret_type="lower-case")

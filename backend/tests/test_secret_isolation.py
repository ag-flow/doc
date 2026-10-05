"""Sécurité — anti-traversal vault + isolation des secrets par propriétaire.

STANDARD « Gestion des secrets » §1/§6 : une référence ${secret://}/${hmac://}
ne peut désigner que le secret de son propriétaire ; un chemin ${vault://} ne
peut pas contenir de traversée « .. ».
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import asyncpg
import pytest
from fastapi import HTTPException

from docflow.secrets.resolver import _assert_safe_vault_path, resolve
from docflow.secrets.secret import Secret
from docflow.vault.service import assert_refs_owned

# ── Anti-traversal (unitaire) ─────────────────────────────────────────────────


def test_safe_vault_path_accepts_normal() -> None:
    _assert_safe_vault_path("/prod/api/key")  # ne lève pas


def test_safe_vault_path_rejects_dotdot() -> None:
    with pytest.raises(ValueError, match="traversée"):
        _assert_safe_vault_path("/prod/../autre/key")


async def test_resolve_vault_ref_rejects_traversal() -> None:
    # La garde s'applique AVANT tout accès au wallet (pool jamais touché).
    with pytest.raises(ValueError, match="traversée"):
        await resolve(
            Secret("${vault://prod:/a/../../etc/passwd}"),
            harpocrate_url="https://vault.example",
            pool=MagicMock(),
            enc_key="k",
        )


# ── Isolation par propriétaire (DB) ───────────────────────────────────────────


async def _user(pool: asyncpg.Pool) -> uuid.UUID:
    return await pool.fetchval(
        "INSERT INTO app_user (email, label, validated) VALUES ($1, $2, true) RETURNING id",
        f"iso-{uuid.uuid4().hex}@t.c",
        "Iso",
    )


async def _secret(pool: asyncpg.Pool, owner: uuid.UUID, kind: str = "generic") -> uuid.UUID:
    return await pool.fetchval(
        "INSERT INTO user_secret (owner_ref, slug, label, value_enc, kind) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id",
        owner,
        f"s-{uuid.uuid4().hex[:8]}",
        "S",
        "enc-token",
        kind,
    )


async def test_owner_can_reference_own_secret(db_pool: asyncpg.Pool) -> None:
    a = await _user(db_pool)
    sid = await _secret(db_pool, a)
    await assert_refs_owned(db_pool, [f"${{secret://{sid}}}"], a)  # ne lève pas


async def test_foreign_secret_is_rejected(db_pool: asyncpg.Pool) -> None:
    a = await _user(db_pool)
    b = await _user(db_pool)
    sid = await _secret(db_pool, a)
    with pytest.raises(HTTPException) as exc:
        await assert_refs_owned(db_pool, [f"${{secret://{sid}}}"], b)
    assert exc.value.status_code == 403


async def test_hmac_ref_also_scoped(db_pool: asyncpg.Pool) -> None:
    a = await _user(db_pool)
    b = await _user(db_pool)
    sid = await _secret(db_pool, a, kind="hmac")
    await assert_refs_owned(db_pool, [f"${{hmac://{sid}}}"], a)
    with pytest.raises(HTTPException):
        await assert_refs_owned(db_pool, [f"${{hmac://{sid}}}"], b)


async def test_unknown_secret_rejected(db_pool: asyncpg.Pool) -> None:
    a = await _user(db_pool)
    with pytest.raises(HTTPException) as exc:
        await assert_refs_owned(db_pool, [f"${{secret://{uuid.uuid4()}}}"], a)
    assert exc.value.status_code == 403


async def test_vault_ref_and_inline_ignored(db_pool: asyncpg.Pool) -> None:
    a = await _user(db_pool)
    # ${vault://} = coffre d'instance (hors isolation user) ; valeur inline = rien.
    await assert_refs_owned(db_pool, ["${vault://prod:/k}", "Bearer xyz", None], a)

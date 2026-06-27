from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from docflow.auth.deps import require_admin, require_superadmin
from docflow.schemas.auth import AuthUser
from docflow.schemas.vault import (
    VaultSecretCreate,
    VaultSecretOut,
    VaultWalletCreate,
    VaultWalletOut,
)
from docflow.vault import service

router = APIRouter(tags=["vault"])

_SuperAdmin = Depends(require_superadmin)
_Admin = Depends(require_admin)


def _key(request: Request) -> str:
    key = request.app.state.settings.encryption_key
    if key is None:
        raise HTTPException(500, "DOCFLOW_ENCRYPTION_KEY non configurée.")
    return str(key.reveal())


# ── Wallets (superadmin) ──────────────────────────────────────────────────────


@router.get("/admin/vault/wallets", response_model=list[VaultWalletOut])
async def list_wallets(request: Request, _: AuthUser = _SuperAdmin) -> list[VaultWalletOut]:
    return await service.list_wallets(request.app.state.pool)


@router.post("/admin/vault/wallets", response_model=VaultWalletOut, status_code=201)
async def create_wallet(
    body: VaultWalletCreate, request: Request, _: AuthUser = _SuperAdmin
) -> VaultWalletOut:
    return await service.create_wallet(request.app.state.pool, body, _key(request))


@router.delete("/admin/vault/wallets/{wallet_id}", status_code=204)
async def delete_wallet(wallet_id: uuid.UUID, request: Request, _: AuthUser = _SuperAdmin) -> None:
    await service.delete_wallet(request.app.state.pool, wallet_id)


# ── Secrets utilisateur (tout admin, scoped owner) ────────────────────────────


@router.get("/admin/secrets", response_model=list[VaultSecretOut])
async def list_secrets(request: Request, user: AuthUser = _Admin) -> list[VaultSecretOut]:
    return await service.list_secrets(request.app.state.pool, user.id)


@router.post("/admin/secrets", response_model=VaultSecretOut, status_code=201)
async def create_secret(
    body: VaultSecretCreate, request: Request, user: AuthUser = _Admin
) -> VaultSecretOut:
    return await service.create_secret(request.app.state.pool, user.id, body, _key(request))


@router.delete("/admin/secrets/{secret_id}", status_code=204)
async def delete_secret(secret_id: uuid.UUID, request: Request, user: AuthUser = _Admin) -> None:
    await service.delete_secret(request.app.state.pool, user.id, secret_id)

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from docflow.auth.deps import require_superadmin
from docflow.schemas.auth import AuthUser
from docflow.schemas.vault import VaultWalletCreate, VaultWalletOut
from docflow.vault import service

router = APIRouter(tags=["vault"])

_SuperAdmin = Depends(require_superadmin)


@router.get("/admin/vault/wallets", response_model=list[VaultWalletOut])
async def list_wallets(
    request: Request, _: AuthUser = _SuperAdmin
) -> list[VaultWalletOut]:
    return await service.list_wallets(request.app.state.pool)


def _key(request: Request) -> str:
    key = request.app.state.settings.encryption_key
    if key is None:
        from fastapi import HTTPException
        raise HTTPException(500, "DOCFLOW_ENCRYPTION_KEY non configurée.")
    return str(key.reveal())


@router.post("/admin/vault/wallets", response_model=VaultWalletOut, status_code=201)
async def create_wallet(
    body: VaultWalletCreate, request: Request, _: AuthUser = _SuperAdmin
) -> VaultWalletOut:
    return await service.create_wallet(request.app.state.pool, body, _key(request))


@router.delete("/admin/vault/wallets/{wallet_id}", status_code=204)
async def delete_wallet(
    wallet_id: uuid.UUID, request: Request, _: AuthUser = _SuperAdmin
) -> None:
    await service.delete_wallet(request.app.state.pool, wallet_id)

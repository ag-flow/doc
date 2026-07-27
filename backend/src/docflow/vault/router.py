from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from docflow.auth.deps import require_authenticated, require_superadmin
from docflow.schemas.auth import AuthUser
from docflow.schemas.vault import (
    HmacSecretCreate,
    HmacSecretCreated,
    HmacSecretOut,
    HmacSecretReveal,
    VaultSecretCreate,
    VaultSecretOut,
    VaultWalletCreate,
    VaultWalletOut,
    WalletCheckOut,
)
from docflow.vault import service

router = APIRouter(tags=["vault"])

_SuperAdmin = Depends(require_superadmin)
_Auth = Depends(require_authenticated)


def _key(request: Request) -> str:
    key = request.app.state.settings.encryption_key
    if key is None:
        raise HTTPException(500, "ENCRYPTION_KEY non configurée.")
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


@router.post("/admin/vault/wallets/{wallet_id}/check", response_model=WalletCheckOut)
async def check_wallet(
    wallet_id: uuid.UUID, request: Request, _: AuthUser = _SuperAdmin
) -> WalletCheckOut:
    """Teste la clé du wallet auprès de Harpocrate (jamais la clé en clair)."""
    return await service.check_wallet(
        request.app.state.pool,
        wallet_id,
        _key(request),
        getattr(request.app.state.settings, "harpocrate_url", None),
    )


@router.get("/admin/secrets", response_model=list[VaultSecretOut])
async def list_secrets(request: Request, user: AuthUser = _Auth) -> list[VaultSecretOut]:
    return await service.list_secrets(request.app.state.pool, user.id, _key(request))


@router.post("/admin/secrets", response_model=VaultSecretOut, status_code=201)
async def create_secret(
    body: VaultSecretCreate, request: Request, user: AuthUser = _Auth
) -> VaultSecretOut:
    return await service.create_secret(request.app.state.pool, user.id, body, _key(request))


@router.delete("/admin/secrets/{secret_id}", status_code=204)
async def delete_secret(secret_id: uuid.UUID, request: Request, user: AuthUser = _Auth) -> None:
    await service.delete_secret(request.app.state.pool, user.id, secret_id, _key(request))


# ── Secrets HMAC (par utilisateur ; valeur copiable par le propriétaire) ──────


@router.get("/hmac-secrets", response_model=list[HmacSecretOut])
async def list_hmac_secrets(request: Request, user: AuthUser = _Auth) -> list[HmacSecretOut]:
    return await service.list_hmac_secrets(request.app.state.pool, user.id)


@router.post("/hmac-secrets", response_model=HmacSecretCreated, status_code=201)
async def create_hmac_secret(
    body: HmacSecretCreate, request: Request, user: AuthUser = _Auth
) -> HmacSecretCreated:
    return await service.create_hmac_secret(request.app.state.pool, user.id, body, _key(request))


@router.get("/hmac-secrets/{secret_id}/reveal", response_model=HmacSecretReveal)
async def reveal_hmac_secret(
    secret_id: uuid.UUID, request: Request, user: AuthUser = _Auth
) -> HmacSecretReveal:
    value = await service.reveal_hmac_secret(
        request.app.state.pool, user.id, secret_id, _key(request)
    )
    return HmacSecretReveal(value=value)


@router.delete("/hmac-secrets/{secret_id}", status_code=204)
async def delete_hmac_secret(
    secret_id: uuid.UUID, request: Request, user: AuthUser = _Auth
) -> None:
    await service.delete_secret(request.app.state.pool, user.id, secret_id, _key(request))

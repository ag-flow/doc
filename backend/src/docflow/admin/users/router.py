from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from docflow.admin.users import service
from docflow.auth.deps import require_superadmin
from docflow.schemas.admin_user import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserSetPassword,
    AdminUserUpdate,
)
from docflow.schemas.auth import AuthUser

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("", response_model=list[AdminUserOut])
async def list_users(
    request: Request, _: AuthUser = Depends(require_superadmin)
) -> list[AdminUserOut]:
    return await service.list_users(request.app.state.pool)


@router.post("", response_model=AdminUserOut, status_code=201)
async def create_user(
    body: AdminUserCreate,
    request: Request,
    _: AuthUser = Depends(require_superadmin),
) -> AdminUserOut:
    return await service.create_user(request.app.state.pool, body)


@router.get("/{user_id}", response_model=AdminUserOut)
async def get_user(
    user_id: uuid.UUID,
    request: Request,
    _: AuthUser = Depends(require_superadmin),
) -> AdminUserOut:
    return await service.get_user(request.app.state.pool, user_id)


@router.patch("/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    request: Request,
    _: AuthUser = Depends(require_superadmin),
) -> AdminUserOut:
    return await service.update_user(request.app.state.pool, user_id, body)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    _: AuthUser = Depends(require_superadmin),
) -> None:
    await service.delete_user(request.app.state.pool, user_id)


@router.post("/{user_id}/set-password", response_model=AdminUserOut)
async def set_password(
    user_id: uuid.UUID,
    body: AdminUserSetPassword,
    request: Request,
    _: AuthUser = Depends(require_superadmin),
) -> AdminUserOut:
    return await service.set_password(request.app.state.pool, user_id, body.password)

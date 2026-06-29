from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status

from docflow.apikeys import service
from docflow.apikeys.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ApiProfileCreate,
    ApiProfileDetail,
    ApiProfileOut,
    ApiProfileScopeOut,
    ScopesUpdate,
)
from docflow.auth.deps import require_admin
from docflow.schemas.auth import AuthUser

router = APIRouter(tags=["api-keys"])

_Auth = Depends(require_admin)


@router.get("/user/api-profiles", response_model=list[ApiProfileOut])
async def list_profiles(
    request: Request, user: AuthUser = _Auth
) -> list[ApiProfileOut]:
    return await service.list_profiles(request.app.state.pool, user.id)


@router.post(
    "/user/api-profiles",
    response_model=ApiProfileOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    body: ApiProfileCreate, request: Request, user: AuthUser = _Auth
) -> ApiProfileOut:
    return await service.create_profile(request.app.state.pool, user.id, body)


@router.get("/user/api-profiles/{profile_id}", response_model=ApiProfileDetail)
async def get_profile(
    profile_id: uuid.UUID, request: Request, user: AuthUser = _Auth
) -> ApiProfileDetail:
    return await service.get_profile(request.app.state.pool, user.id, profile_id)


@router.put(
    "/user/api-profiles/{profile_id}/scopes",
    response_model=list[ApiProfileScopeOut],
)
async def set_scopes(
    profile_id: uuid.UUID,
    body: ScopesUpdate,
    request: Request,
    user: AuthUser = _Auth,
) -> list[ApiProfileScopeOut]:
    return await service.set_scopes(request.app.state.pool, user.id, profile_id, body.scopes)


@router.delete(
    "/user/api-profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_profile(
    profile_id: uuid.UUID, request: Request, user: AuthUser = _Auth
) -> None:
    await service.delete_profile(request.app.state.pool, user.id, profile_id)


@router.get("/user/api-keys", response_model=list[ApiKeyOut])
async def list_keys(
    request: Request, user: AuthUser = _Auth
) -> list[ApiKeyOut]:
    return await service.list_keys(request.app.state.pool, user.id)


@router.post(
    "/user/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
async def generate_key(
    body: ApiKeyCreate, request: Request, user: AuthUser = _Auth
) -> ApiKeyCreated:
    return await service.generate_key(request.app.state.pool, user.id, body)


@router.delete("/user/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    key_id: uuid.UUID, request: Request, user: AuthUser = _Auth
) -> None:
    await service.revoke_key(request.app.state.pool, user.id, key_id)

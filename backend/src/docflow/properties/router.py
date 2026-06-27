from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from docflow.auth.deps import require_admin
from docflow.properties import service
from docflow.schemas.auth import AuthUser
from docflow.schemas.constraint import ConstraintCreate, ConstraintOut
from docflow.schemas.properties import (
    AllowedValueCreate,
    AllowedValueOut,
    AllowedValueUpdate,
    PropertiesDefCreate,
    PropertiesDefOut,
    PropertiesDefUpdate,
)

router = APIRouter(tags=["properties"])

_WS = "/workspaces/{ws_slug}"
_TYPE = _WS + "/types/{type_slug}"
_PROP = _TYPE + "/properties/{prop_slug}"
_VAL = _PROP + "/values/{val_slug}"
_Auth = Depends(require_admin)


# ── Properties defs ───────────────────────────────────────────────────────────


@router.get(_TYPE + "/properties", response_model=list[PropertiesDefOut])
async def list_defs(
    ws_slug: str, type_slug: str, request: Request, _: AuthUser = _Auth
) -> list[PropertiesDefOut]:
    return await service.list_defs(request.app.state.pool, ws_slug, type_slug)


@router.post(_TYPE + "/properties", response_model=PropertiesDefOut, status_code=201)
async def create_def(
    ws_slug: str,
    type_slug: str,
    body: PropertiesDefCreate,
    request: Request,
    _: AuthUser = _Auth,
) -> PropertiesDefOut:
    return await service.create_def(request.app.state.pool, ws_slug, type_slug, body)


@router.get(_PROP, response_model=PropertiesDefOut)
async def get_def(
    ws_slug: str, type_slug: str, prop_slug: str, request: Request, _: AuthUser = _Auth
) -> PropertiesDefOut:
    return await service.get_def(request.app.state.pool, ws_slug, type_slug, prop_slug)


@router.patch(_PROP, response_model=PropertiesDefOut)
async def update_def(
    ws_slug: str,
    type_slug: str,
    prop_slug: str,
    body: PropertiesDefUpdate,
    request: Request,
    _: AuthUser = _Auth,
) -> PropertiesDefOut:
    return await service.update_def(request.app.state.pool, ws_slug, type_slug, prop_slug, body)


@router.delete(_PROP, status_code=204)
async def delete_def(
    ws_slug: str, type_slug: str, prop_slug: str, request: Request, _: AuthUser = _Auth
) -> None:
    await service.delete_def(request.app.state.pool, ws_slug, type_slug, prop_slug)


# ── Allowed values ────────────────────────────────────────────────────────────


@router.get(_PROP + "/values", response_model=list[AllowedValueOut])
async def list_values(
    ws_slug: str, type_slug: str, prop_slug: str, request: Request, _: AuthUser = _Auth
) -> list[AllowedValueOut]:
    return await service.list_allowed_values(request.app.state.pool, ws_slug, type_slug, prop_slug)


@router.post(_PROP + "/values", response_model=AllowedValueOut, status_code=201)
async def create_value(
    ws_slug: str,
    type_slug: str,
    prop_slug: str,
    body: AllowedValueCreate,
    request: Request,
    _: AuthUser = _Auth,
) -> AllowedValueOut:
    return await service.create_allowed_value(
        request.app.state.pool, ws_slug, type_slug, prop_slug, body
    )


@router.get(_VAL, response_model=AllowedValueOut)
async def get_value(
    ws_slug: str,
    type_slug: str,
    prop_slug: str,
    val_slug: str,
    request: Request,
    _: AuthUser = _Auth,
) -> AllowedValueOut:
    return await service.get_allowed_value(
        request.app.state.pool, ws_slug, type_slug, prop_slug, val_slug
    )


@router.patch(_VAL, response_model=AllowedValueOut)
async def update_value(
    ws_slug: str,
    type_slug: str,
    prop_slug: str,
    val_slug: str,
    body: AllowedValueUpdate,
    request: Request,
    _: AuthUser = _Auth,
) -> AllowedValueOut:
    return await service.update_allowed_value(
        request.app.state.pool, ws_slug, type_slug, prop_slug, val_slug, body
    )


@router.delete(_VAL, status_code=204)
async def delete_value(
    ws_slug: str,
    type_slug: str,
    prop_slug: str,
    val_slug: str,
    request: Request,
    _: AuthUser = _Auth,
) -> None:
    await service.delete_allowed_value(
        request.app.state.pool, ws_slug, type_slug, prop_slug, val_slug
    )


# ── Constraints ───────────────────────────────────────────────────────────────

_CSTR = _PROP + "/constraints"


@router.get(_CSTR, response_model=list[ConstraintOut])
async def list_constraints(
    ws_slug: str, type_slug: str, prop_slug: str, request: Request, _: AuthUser = _Auth
) -> list[ConstraintOut]:
    return await service.list_constraints(request.app.state.pool, ws_slug, type_slug, prop_slug)


@router.post(_CSTR, response_model=ConstraintOut, status_code=201)
async def upsert_constraint(
    ws_slug: str,
    type_slug: str,
    prop_slug: str,
    body: ConstraintCreate,
    request: Request,
    _: AuthUser = _Auth,
) -> ConstraintOut:
    return await service.upsert_constraint(
        request.app.state.pool, ws_slug, type_slug, prop_slug, body
    )


@router.delete(_CSTR + "/{kind}", status_code=204)
async def delete_constraint(
    ws_slug: str,
    type_slug: str,
    prop_slug: str,
    kind: str,
    request: Request,
    _: AuthUser = _Auth,
) -> None:
    await service.delete_constraint(request.app.state.pool, ws_slug, type_slug, prop_slug, kind)

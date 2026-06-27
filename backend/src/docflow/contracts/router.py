from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from docflow.auth.deps import require_admin
from docflow.contracts import service
from docflow.schemas.auth import AuthUser
from docflow.schemas.contracts import (
    ContractDetailOut,
    ContractImport,
    ContractOut,
    ContractUpdate,
)

router = APIRouter(tags=["contracts"])

_Auth = Depends(require_admin)


@router.get("/admin/contracts", response_model=list[ContractOut])
async def list_contracts(request: Request, _: AuthUser = _Auth) -> list[ContractOut]:
    return await service.list_contracts(request.app.state.pool)


@router.post("/admin/contracts", response_model=ContractOut, status_code=201)
async def import_contract(
    body: ContractImport, request: Request, _: AuthUser = _Auth
) -> ContractOut:
    return await service.import_contract(request.app.state.pool, body)


@router.get("/admin/contracts/{contract_id}", response_model=ContractDetailOut)
async def get_contract(
    contract_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> ContractDetailOut:
    return await service.get_contract_detail(request.app.state.pool, contract_id)


@router.patch("/admin/contracts/{contract_id}", response_model=ContractOut)
async def update_contract(
    contract_id: uuid.UUID, body: ContractUpdate, request: Request, _: AuthUser = _Auth
) -> ContractOut:
    return await service.update_contract(request.app.state.pool, contract_id, body)


@router.post("/admin/contracts/{contract_id}/refresh", response_model=ContractOut)
async def refresh_contract(
    contract_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> ContractOut:
    return await service.refresh_contract(request.app.state.pool, contract_id)


@router.delete("/admin/contracts/{contract_id}", status_code=204)
async def delete_contract(
    contract_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> None:
    await service.delete_contract(request.app.state.pool, contract_id)

from __future__ import annotations

from fastapi import APIRouter, Request

from docflow.schemas.admin_user import AdminUserOut
from docflow.schemas.setup import InitAdminRequest, SetupStatusOut
from docflow.setup import service

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatusOut)
async def setup_status(request: Request) -> SetupStatusOut:
    async with request.app.state.pool.acquire() as conn:
        count = await service.user_count(conn)
    return SetupStatusOut(needs_setup=count == 0)


@router.post("/init-admin", response_model=AdminUserOut, status_code=201)
async def init_admin(body: InitAdminRequest, request: Request) -> AdminUserOut:
    return await service.init_admin(request.app.state.pool, body)

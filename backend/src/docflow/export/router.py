from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from docflow.auth.deps import require_admin
from docflow.export import service
from docflow.schemas.auth import AuthUser

router = APIRouter(tags=["export"])

_Auth = Depends(require_admin)


@router.get("/workspaces/{ws_slug}/export")
async def export_workspace(
    ws_slug: str,
    request: Request,
    _: AuthUser = _Auth,
    scope: str = Query(default="workspace", pattern="^(workspace|bloc)$"),
    bloc: str | None = Query(default=None),
) -> Response:
    """Exporte le workspace (ou un bloc) en archive ZIP de fichiers markdown."""
    bloc_slug = bloc if scope == "bloc" else None
    zip_bytes = await service.build_export_zip(request.app.state.pool, ws_slug, bloc_slug)
    filename = f"{ws_slug}.zip" if bloc_slug is None else f"{ws_slug}-{bloc_slug}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

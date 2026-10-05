from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from docflow.auth.deps import require_authenticated
from docflow.export import pdf, service
from docflow.schemas.auth import AuthUser
from docflow.workspaces.access import require_ws_access

router = APIRouter(tags=["export"], dependencies=[Depends(require_ws_access)])

_Auth = Depends(require_authenticated)


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


@router.get("/workspaces/{ws_slug}/documents/{doc_id}/export/pdf")
async def export_document_pdf(
    ws_slug: str,
    doc_id: uuid.UUID,
    request: Request,
    _: AuthUser = _Auth,
    children: str = Query(
        default="", description="ids d'enfants directs, ordonnés, séparés par des virgules"
    ),
    signed: bool = Query(default=False),
) -> Response:
    """Exporte le document (et les enfants cochés, dans l'ordre choisi) en PDF."""
    try:
        child_ids = [uuid.UUID(c) for c in children.split(",") if c.strip()]
    except ValueError as exc:
        raise HTTPException(422, "children : liste d'UUID séparés par des virgules") from exc
    filename, docs = await pdf.fetch_export_docs(
        request.app.state.pool, ws_slug, doc_id, child_ids
    )
    html_doc = pdf.build_html(docs, signed=signed)
    # Rendu CPU-bound (Pango) : hors event loop.
    pdf_bytes = await run_in_threadpool(pdf.render_pdf, html_doc)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )

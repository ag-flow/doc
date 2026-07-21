"""Router REST des datasets tabulaires (préfixe ``/api`` monté dans ``app.py``).

Racine : ``/workspaces/{ws_slug}/datasets``. Chaque endpoint exige un utilisateur
authentifié (``require_authenticated``) puis vérifie le périmètre d'une éventuelle
clé API via ``check_api_key_scope`` (lecture / écriture). Aucune logique métier
ici : tout est délégué au service (``service`` / ``query`` / ``csv_io``) ; le
router ne fait que valider les DTOs et projeter les dicts de retour.

Ordre des routes : les segments littéraux (``/import-csv``) sont déclarés avant
les segments paramétriques (``/{dataset_id}``) pour lever toute ambiguïté.
"""

from __future__ import annotations

import uuid
from typing import Literal, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from docflow.auth.deps import check_api_key_scope, require_authenticated
from docflow.datasets import service
from docflow.datasets.csv_io import export_csv, import_csv
from docflow.datasets.query import query_dataset
from docflow.schemas.auth import AuthUser
from docflow.schemas.dataset import (
    ColumnCreate,
    ColumnDeletedOut,
    ColumnDetailOut,
    ColumnUpdate,
    DatasetCreate,
    DatasetDetailOut,
    DatasetListItem,
    DatasetOut,
    ImportCsvRequest,
    ImportCsvResultOut,
    QueryRequest,
    QueryResultOut,
    RowCreate,
    RowCreatedOut,
    RowDeletedOut,
    RowUpdate,
    RowUpdatedOut,
)

router = APIRouter(tags=["datasets"])

_WS = "/workspaces/{ws_slug}/datasets"
_DS = _WS + "/{dataset_id}"
_Auth = Depends(require_authenticated)


# ── Datasets ──────────────────────────────────────────────────────────────────


@router.post(_WS, response_model=DatasetOut, status_code=201)
async def create_dataset(
    ws_slug: str, body: DatasetCreate, request: Request, user: AuthUser = _Auth
) -> DatasetOut:
    check_api_key_scope(request, ws_slug, write=True)
    result = await service.create_dataset(
        request.app.state.pool, ws_slug, body.slug, body.label, user.id
    )
    return DatasetOut.model_validate(result)


@router.get(_WS, response_model=list[DatasetListItem])
async def list_datasets(
    ws_slug: str, request: Request, _: AuthUser = _Auth
) -> list[DatasetListItem]:
    check_api_key_scope(request, ws_slug)
    rows = await service.list_datasets(request.app.state.pool, ws_slug)
    return [DatasetListItem.model_validate(r) for r in rows]


@router.post(_WS + "/import-csv", response_model=ImportCsvResultOut)
async def import_dataset_csv(
    ws_slug: str, body: ImportCsvRequest, request: Request, user: AuthUser = _Auth
) -> ImportCsvResultOut:
    check_api_key_scope(request, ws_slug, write=True)
    result = await import_csv(
        request.app.state.pool,
        ws_slug,
        dataset_id=body.dataset_id,
        slug=body.slug,
        label=body.label,
        csv_text=body.csv,
        has_header=body.has_header,
        mode=cast("Literal['replace', 'append']", body.mode),
        created_by=user.id,
    )
    return ImportCsvResultOut.model_validate(result)


@router.get(_DS, response_model=DatasetDetailOut)
async def get_dataset(
    ws_slug: str, dataset_id: uuid.UUID, request: Request, _: AuthUser = _Auth
) -> DatasetDetailOut:
    check_api_key_scope(request, ws_slug)
    result = await service.get_dataset(request.app.state.pool, ws_slug, dataset_id)
    return DatasetDetailOut.model_validate(result)


@router.get(_DS + "/export-csv")
async def export_dataset_csv(
    ws_slug: str,
    dataset_id: uuid.UUID,
    request: Request,
    _: AuthUser = _Auth,
    header: Literal["slug", "label"] = Query(default="slug"),
) -> Response:
    check_api_key_scope(request, ws_slug)
    csv_text = await export_csv(request.app.state.pool, ws_slug, dataset_id, header=header)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="dataset-{dataset_id}.csv"'},
    )


# ── Colonnes ──────────────────────────────────────────────────────────────────


@router.post(_DS + "/columns", response_model=ColumnDetailOut, status_code=201)
async def add_column(
    ws_slug: str,
    dataset_id: uuid.UUID,
    body: ColumnCreate,
    request: Request,
    _: AuthUser = _Auth,
) -> ColumnDetailOut:
    check_api_key_scope(request, ws_slug, write=True)
    result = await service.add_column(
        request.app.state.pool,
        ws_slug,
        dataset_id,
        body.slug,
        body.label,
        body.type,
        position=body.position,
        required=body.required,
    )
    return ColumnDetailOut.model_validate(result)


@router.patch(_DS + "/columns/{column_slug}", response_model=ColumnDetailOut)
async def update_column(
    ws_slug: str,
    dataset_id: uuid.UUID,
    column_slug: str,
    body: ColumnUpdate,
    request: Request,
    _: AuthUser = _Auth,
) -> ColumnDetailOut:
    check_api_key_scope(request, ws_slug, write=True)
    result = await service.update_column(
        request.app.state.pool,
        ws_slug,
        dataset_id,
        column_slug,
        label=body.label,
        type=body.type,
        position=body.position,
        required=body.required,
    )
    return ColumnDetailOut.model_validate(result)


@router.delete(_DS + "/columns/{column_slug}", response_model=ColumnDeletedOut)
async def delete_column(
    ws_slug: str,
    dataset_id: uuid.UUID,
    column_slug: str,
    request: Request,
    _: AuthUser = _Auth,
) -> ColumnDeletedOut:
    check_api_key_scope(request, ws_slug, write=True)
    result = await service.delete_column(request.app.state.pool, ws_slug, dataset_id, column_slug)
    return ColumnDeletedOut.model_validate(result)


# ── Lignes ────────────────────────────────────────────────────────────────────


@router.post(_DS + "/rows", response_model=RowCreatedOut, status_code=201)
async def add_row(
    ws_slug: str,
    dataset_id: uuid.UUID,
    body: RowCreate,
    request: Request,
    _: AuthUser = _Auth,
) -> RowCreatedOut:
    check_api_key_scope(request, ws_slug, write=True)
    result = await service.add_row(
        request.app.state.pool,
        ws_slug,
        dataset_id,
        cast("dict[str, str]", body.cells),
        position=body.position,
    )
    return RowCreatedOut.model_validate(result)


@router.patch(_DS + "/rows/{row_id}", response_model=RowUpdatedOut)
async def update_row(
    ws_slug: str,
    dataset_id: uuid.UUID,
    row_id: uuid.UUID,
    body: RowUpdate,
    request: Request,
    _: AuthUser = _Auth,
) -> RowUpdatedOut:
    check_api_key_scope(request, ws_slug, write=True)
    result = await service.update_row(
        request.app.state.pool,
        ws_slug,
        dataset_id,
        row_id,
        cast("dict[str, str]", body.cells),
    )
    return RowUpdatedOut.model_validate(result)


@router.delete(_DS + "/rows/{row_id}", response_model=RowDeletedOut)
async def delete_row(
    ws_slug: str,
    dataset_id: uuid.UUID,
    row_id: uuid.UUID,
    request: Request,
    _: AuthUser = _Auth,
) -> RowDeletedOut:
    check_api_key_scope(request, ws_slug, write=True)
    result = await service.delete_row(request.app.state.pool, ws_slug, dataset_id, row_id)
    return RowDeletedOut.model_validate(result)


# ── Requêtage ─────────────────────────────────────────────────────────────────


@router.post(_DS + "/query", response_model=QueryResultOut)
async def query(
    ws_slug: str,
    dataset_id: uuid.UUID,
    body: QueryRequest,
    request: Request,
    _: AuthUser = _Auth,
) -> QueryResultOut:
    check_api_key_scope(request, ws_slug)
    result = await query_dataset(
        request.app.state.pool,
        ws_slug,
        dataset_id,
        filters=[f.model_dump() for f in body.filters],
        sort=body.sort.model_dump() if body.sort is not None else None,
        page=body.page,
        page_size=body.page_size,
    )
    return QueryResultOut.model_validate(result)

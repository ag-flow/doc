"""DTOs pydantic (entrées / sorties) du router REST datasets.

Tous les modèles portent ``extra="forbid"`` : un champ inattendu dans un corps
de requête est rejeté (422). Les modèles de sortie miroir des dicts renvoyés par
``docflow.datasets.service`` / ``query`` / ``csv_io`` — construits par
``model_validate`` au retour des handlers.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

_Forbid = ConfigDict(extra="forbid")

# ── Entrées ───────────────────────────────────────────────────────────────────


class DatasetCreate(BaseModel):
    model_config = _Forbid

    slug: str
    label: str


class ColumnCreate(BaseModel):
    model_config = _Forbid

    slug: str
    label: str
    type: str
    position: int | None = None
    required: bool = False


class ColumnUpdate(BaseModel):
    model_config = _Forbid

    label: str | None = None
    type: str | None = None
    position: int | None = None
    required: bool | None = None


class RowCreate(BaseModel):
    model_config = _Forbid

    cells: dict[str, str | None]
    position: int | None = None


class RowUpdate(BaseModel):
    model_config = _Forbid

    cells: dict[str, str | None]


class QueryFilter(BaseModel):
    model_config = _Forbid

    column: str
    op: str
    value: str | int | float | bool | None = None


class QuerySort(BaseModel):
    model_config = _Forbid

    column: str
    dir: str = "asc"


class QueryRequest(BaseModel):
    model_config = _Forbid

    filters: list[QueryFilter] = []
    sort: QuerySort | None = None
    page: int = 1
    page_size: int = 50


class ImportCsvRequest(BaseModel):
    model_config = _Forbid

    dataset_id: uuid.UUID | None = None
    slug: str | None = None
    label: str | None = None
    csv: str
    has_header: bool = True
    mode: str = "replace"


# ── Sorties ───────────────────────────────────────────────────────────────────


class DatasetOut(BaseModel):
    model_config = _Forbid

    id: str
    slug: str
    label: str


class DatasetListItem(BaseModel):
    model_config = _Forbid

    id: str
    slug: str
    label: str
    column_count: int
    row_count: int


class ColumnOut(BaseModel):
    model_config = _Forbid

    slug: str
    label: str
    type: str
    position: int
    required: bool


class ColumnDetailOut(BaseModel):
    model_config = _Forbid

    id: str
    slug: str
    label: str
    type: str
    position: int
    required: bool


class RowOut(BaseModel):
    model_config = _Forbid

    id: str
    cells: dict[str, str | None]


class DatasetDetailOut(BaseModel):
    model_config = _Forbid

    id: str
    slug: str
    label: str
    columns: list[ColumnOut]
    rows: list[RowOut]


class ColumnDeletedOut(BaseModel):
    model_config = _Forbid

    deleted: bool
    column_slug: str


class RowCreatedOut(BaseModel):
    model_config = _Forbid

    row_id: str


class RowUpdatedOut(BaseModel):
    model_config = _Forbid

    row_id: str
    updated: bool


class RowDeletedOut(BaseModel):
    model_config = _Forbid

    deleted: bool
    row_id: str


class QueryResultOut(BaseModel):
    model_config = _Forbid

    total: int
    page: int
    page_size: int
    rows: list[RowOut]


class ImportCsvResultOut(BaseModel):
    model_config = _Forbid

    dataset_id: str
    columns_created: int
    rows_created: int
    rows_skipped: int
    errors: list[dict[str, object]]
    errors_total: int | None = None

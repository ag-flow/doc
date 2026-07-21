/**
 * Client REST des datasets tabulaires — miroir de `backend/schemas/dataset.py`.
 *
 * Réutilise `api` (Bearer + gestion 401/erreurs) de `./api`. L'export CSV passe
 * par `api.getBlob` (téléchargement de fichier), les autres endpoints par JSON.
 */
import { api } from './api'

// ── Types colonnes ─────────────────────────────────────────────────────────

/** Types de colonne supportés — miroir de `coercion.ColumnType` (backend). */
export type DatasetColumnType = 'text' | 'int' | 'float' | 'date' | 'bool' | 'url'

export const DATASET_COLUMN_TYPES: readonly DatasetColumnType[] = [
  'text',
  'int',
  'float',
  'date',
  'bool',
  'url',
] as const

// ── DTO de sortie ──────────────────────────────────────────────────────────

export interface DatasetOut {
  id: string
  slug: string
  label: string
}

export interface DatasetListItem {
  id: string
  slug: string
  label: string
  column_count: number
  row_count: number
}

export interface DatasetColumnOut {
  slug: string
  label: string
  type: DatasetColumnType
  position: number
  required: boolean
}

export interface DatasetColumnDetailOut extends DatasetColumnOut {
  id: string
}

export interface DatasetRowOut {
  id: string
  cells: Record<string, string | null>
}

export interface DatasetDetailOut {
  id: string
  slug: string
  label: string
  columns: DatasetColumnOut[]
  rows: DatasetRowOut[]
}

export interface ColumnDeletedOut {
  deleted: boolean
  column_slug: string
}

export interface RowCreatedOut {
  row_id: string
}

export interface RowUpdatedOut {
  row_id: string
  updated: boolean
}

export interface RowDeletedOut {
  deleted: boolean
  row_id: string
}

export interface DatasetQueryResultOut {
  total: number
  page: number
  page_size: number
  rows: DatasetRowOut[]
}

export interface ImportCsvResultOut {
  dataset_id: string
  columns_created: number
  rows_created: number
  rows_skipped: number
  errors: { line?: number; reason?: string; [k: string]: unknown }[]
  errors_total: number | null
}

// ── DTO d'entrée ───────────────────────────────────────────────────────────

export interface ColumnCreateBody {
  slug: string
  label: string
  type: DatasetColumnType
  position?: number | null
  required?: boolean
}

export interface ColumnUpdateBody {
  label?: string | null
  type?: DatasetColumnType | null
  position?: number | null
  required?: boolean | null
}

export interface RowCreateBody {
  cells: Record<string, string | null>
  position?: number | null
}

export interface RowUpdateBody {
  cells: Record<string, string | null>
}

export interface DatasetQueryFilter {
  column: string
  op: string
  value?: string | number | boolean | null
}

export interface DatasetQuerySort {
  column: string
  dir?: 'asc' | 'desc'
}

export interface DatasetQueryBody {
  filters?: DatasetQueryFilter[]
  sort?: DatasetQuerySort | null
  page?: number
  page_size?: number
}

export interface ImportCsvBody {
  dataset_id?: string | null
  slug?: string | null
  label?: string | null
  csv: string
  has_header?: boolean
  mode?: 'replace' | 'append'
}

// ── Endpoints ──────────────────────────────────────────────────────────────

const base = (ws: string) => `/workspaces/${ws}/datasets`

export const datasetsApi = {
  createDataset: (ws: string, body: { slug: string; label: string }) =>
    api.post<DatasetOut>(base(ws), body),

  listDatasets: (ws: string) => api.get<DatasetListItem[]>(base(ws)),

  getDataset: (ws: string, datasetId: string) =>
    api.get<DatasetDetailOut>(`${base(ws)}/${datasetId}`),

  addColumn: (ws: string, datasetId: string, body: ColumnCreateBody) =>
    api.post<DatasetColumnDetailOut>(`${base(ws)}/${datasetId}/columns`, body),

  updateColumn: (ws: string, datasetId: string, columnSlug: string, body: ColumnUpdateBody) =>
    api.patch<DatasetColumnDetailOut>(`${base(ws)}/${datasetId}/columns/${columnSlug}`, body),

  deleteColumn: (ws: string, datasetId: string, columnSlug: string) =>
    api.delete<ColumnDeletedOut>(`${base(ws)}/${datasetId}/columns/${columnSlug}`),

  addRow: (ws: string, datasetId: string, body: RowCreateBody) =>
    api.post<RowCreatedOut>(`${base(ws)}/${datasetId}/rows`, body),

  updateRow: (ws: string, datasetId: string, rowId: string, body: RowUpdateBody) =>
    api.patch<RowUpdatedOut>(`${base(ws)}/${datasetId}/rows/${rowId}`, body),

  deleteRow: (ws: string, datasetId: string, rowId: string) =>
    api.delete<RowDeletedOut>(`${base(ws)}/${datasetId}/rows/${rowId}`),

  queryDataset: (ws: string, datasetId: string, body: DatasetQueryBody) =>
    api.post<DatasetQueryResultOut>(`${base(ws)}/${datasetId}/query`, body),

  importDatasetCsv: (ws: string, body: ImportCsvBody) =>
    api.post<ImportCsvResultOut>(`${base(ws)}/import-csv`, body),

  /** Export CSV : renvoie un Blob `text/csv` prêt au téléchargement. */
  exportDatasetCsv: (ws: string, datasetId: string, header: 'slug' | 'label' = 'slug') =>
    api.getBlob(`${base(ws)}/${datasetId}/export-csv?header=${header}`),
}

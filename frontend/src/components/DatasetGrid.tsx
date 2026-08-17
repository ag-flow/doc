import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createColumnHelper, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import { Download, Plus, Trash2, Upload, X } from 'lucide-react'
import {
  datasetsApi,
  DATASET_COLUMN_TYPES,
  type DatasetColumnOut,
  type DatasetColumnType,
  type DatasetRowOut,
} from '../lib/datasetsApi'
import { ApiError } from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { parseCsv, type InferredColumn } from '../lib/csvImport'

interface DatasetGridProps {
  workspaceSlug: string
  datasetId: string
  editable: boolean
}

const columnHelper = createColumnHelper<DatasetRowOut>()

/** Grille dynamique d'un dataset : colonnes d'après `columns`, valeurs = cells[slug]. */
export function DatasetGrid({ workspaceSlug, datasetId, editable }: DatasetGridProps) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const queryKey = ['dataset', workspaceSlug, datasetId]
  const [error, setError] = useState<string | null>(null)
  const [importState, setImportState] = useState<ParsedImport | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => datasetsApi.getDataset(workspaceSlug, datasetId),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey })
  const onError = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e))

  const updateRow = useMutation({
    mutationFn: (v: { rowId: string; cells: Record<string, string | null> }) =>
      datasetsApi.updateRow(workspaceSlug, datasetId, v.rowId, { cells: v.cells }),
    onSuccess: invalidate,
    onError,
  })
  const addRow = useMutation({
    mutationFn: () => datasetsApi.addRow(workspaceSlug, datasetId, { cells: {} }),
    onSuccess: invalidate,
    onError,
  })
  const deleteRow = useMutation({
    mutationFn: (rowId: string) => datasetsApi.deleteRow(workspaceSlug, datasetId, rowId),
    onSuccess: invalidate,
    onError,
  })
  const addColumn = useMutation({
    mutationFn: (v: { slug: string; label: string; type: DatasetColumnType }) =>
      datasetsApi.addColumn(workspaceSlug, datasetId, v),
    onSuccess: invalidate,
    onError,
  })
  const updateColumn = useMutation({
    mutationFn: (v: { slug: string; type: DatasetColumnType }) =>
      datasetsApi.updateColumn(workspaceSlug, datasetId, v.slug, { type: v.type }),
    onSuccess: invalidate,
    onError,
  })
  const deleteColumn = useMutation({
    mutationFn: (slug: string) => datasetsApi.deleteColumn(workspaceSlug, datasetId, slug),
    onSuccess: invalidate,
    onError,
  })
  const importCsv = useMutation({
    mutationFn: (v: { csv: string; mode: 'replace' | 'append' }) =>
      datasetsApi.importDatasetCsv(workspaceSlug, {
        dataset_id: datasetId,
        csv: v.csv,
        has_header: true,
        mode: v.mode,
      }),
    onSuccess: () => {
      setImportState(null)
      invalidate()
    },
    onError,
  })

  const columns = useMemo(() => buildColumns(data?.columns ?? []), [data?.columns])

  const table = useReactTable({
    data: data?.rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  if (isLoading) return <div data-testid="dataset-grid-loading">{t('dataset.loading')}</div>
  if (isError || !data)
    return (
      <div data-testid="dataset-grid-error" className="text-sm text-red-700">
        {t('dataset.loadError')}
      </div>
    )

  async function onExport() {
    setError(null)
    try {
      const blob = await datasetsApi.exportDatasetCsv(workspaceSlug, datasetId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${data!.slug}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      onError(e)
    }
  }

  // PATCH partiel : n'envoyer QUE la cellule modifiée. Envoyer l'instantané de rendu
  // de toute la ligne renvoyait les valeurs des cellules voisines telles qu'elles
  // étaient au dernier rendu — une seconde édition avant la fin du refetch écrasait
  // donc la première côté serveur (perte silencieuse). Le endpoint
  // `PATCH .../rows/{id}` fait un upsert cellule par cellule : les colonnes absentes
  // du corps ne sont pas touchées.
  const editCell = (row: DatasetRowOut, colSlug: string, value: string) => {
    if ((row.cells[colSlug] ?? '') === value) return
    updateRow.mutate({ rowId: row.id, cells: { [colSlug]: value === '' ? null : value } })
  }

  return (
    <div data-testid="dataset-grid" className="my-2 w-full" data-content-type="dataset">
      <div className="flex items-center gap-2 pb-2">
        <span className="font-medium">{data.label}</span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            data-testid="dataset-export-btn"
            onClick={onExport}
            className="inline-flex items-center gap-1 rounded border border-gray-200 px-2 py-1 text-xs hover:bg-gray-50"
          >
            <Download size={14} /> {t('dataset.export')}
          </button>
          {editable && (
            <ImportButton onFile={(text) => setImportState(makeImport(text))} />
          )}
        </div>
      </div>

      {error && (
        <div data-testid="dataset-error" className="mb-2 rounded bg-red-50 px-2 py-1 text-xs text-red-700">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded border border-gray-200">
        <table data-testid="dataset-table" className="min-w-full text-sm">
          <thead className="bg-gray-50">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th key={h.id} className="border-b border-gray-200 px-2 py-1 text-left align-top">
                    <ColumnHeader
                      column={data.columns.find((c) => c.slug === h.column.id) ?? null}
                      editable={editable}
                      onRetype={(type) => updateColumn.mutate({ slug: h.column.id, type })}
                      onDelete={() => deleteColumn.mutate(h.column.id)}
                    />
                  </th>
                ))}
                {editable && (
                  <th className="border-b border-gray-200 px-2 py-1">
                    <AddColumnControl
                      onAdd={(label, type) =>
                        addColumn.mutate({ slug: labelToSlug(label) || 'col', label, type })
                      }
                    />
                  </th>
                )}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.original.id} data-testid={`dataset-row-${row.original.id}`}>
                {row.getVisibleCells().map((cell) => {
                  const col = data.columns.find((c) => c.slug === cell.column.id)
                  const raw = row.original.cells[cell.column.id] ?? ''
                  return (
                    <td key={cell.id} className="border-b border-gray-100 px-2 py-1 align-top">
                      {editable && col ? (
                        <EditableCell
                          testId={`dataset-cell-${cell.column.id}-${row.original.id}`}
                          type={inputType(col.type)}
                          serverValue={raw}
                          onCommit={(v) => editCell(row.original, cell.column.id, v)}
                        />
                      ) : (
                        <span>{raw}</span>
                      )}
                    </td>
                  )
                })}
                {editable && (
                  <td className="border-b border-gray-100 px-2 py-1">
                    <button
                      type="button"
                      data-testid={`dataset-delete-row-${row.original.id}`}
                      onClick={() => deleteRow.mutate(row.original.id)}
                      className="text-gray-400 hover:text-red-600"
                      title={t('dataset.deleteRow')}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {data.rows.length === 0 && (
              <tr>
                <td
                  colSpan={data.columns.length + (editable ? 1 : 0)}
                  className="px-2 py-3 text-center text-xs text-gray-500"
                >
                  {t('dataset.empty')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {editable && (
        <button
          type="button"
          data-testid="dataset-add-row-btn"
          onClick={() => addRow.mutate()}
          className="mt-2 inline-flex items-center gap-1 rounded border border-dashed border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
        >
          <Plus size={14} /> {t('dataset.addRow')}
        </button>
      )}

      {importState && (
        <ImportPreview
          state={importState}
          setState={setImportState}
          onCancel={() => setImportState(null)}
          onConfirm={(mode) => importCsv.mutate({ csv: importState.csv, mode })}
          pending={importCsv.isPending}
        />
      )}
    </div>
  )
}

// ── Cellule éditable ─────────────────────────────────────────────────────────

/** Champ de cellule contrôlé, aligné sur la valeur serveur à chaque refetch —
 *  SAUF pendant une saisie : un rafraîchissement d'arrière-plan (retypage de
 *  colonne, édition concurrente) ne doit pas réinitialiser le champ sous les
 *  doigts de l'utilisateur. */
function EditableCell({
  testId,
  type,
  serverValue,
  onCommit,
}: {
  testId: string
  type: string
  serverValue: string
  onCommit: (value: string) => void
}) {
  const [draft, setDraft] = useState(serverValue)
  const [editing, setEditing] = useState(false)
  const [synced, setSynced] = useState(serverValue)

  if (!editing && synced !== serverValue) {
    setSynced(serverValue)
    setDraft(serverValue)
  }

  return (
    <input
      data-testid={testId}
      type={type}
      value={draft}
      onFocus={() => setEditing(true)}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        setEditing(false)
        onCommit(draft)
      }}
      className="w-full min-w-[6rem] rounded border border-transparent px-1 py-0.5 hover:border-gray-200 focus:border-blue-400 focus:outline-none"
    />
  )
}

// ── Colonnes react-table ─────────────────────────────────────────────────────

function buildColumns(cols: DatasetColumnOut[]) {
  return cols.map((c) =>
    columnHelper.accessor((row) => row.cells[c.slug] ?? '', {
      id: c.slug,
      header: c.label,
    }),
  )
}

function inputType(type: DatasetColumnType): string {
  if (type === 'int' || type === 'float') return 'number'
  if (type === 'date') return 'date'
  if (type === 'url') return 'url'
  return 'text'
}

// ── En-tête de colonne (label + retypage + suppression) ──────────────────────

function ColumnHeader({
  column,
  editable,
  onRetype,
  onDelete,
}: {
  column: DatasetColumnOut | null
  editable: boolean
  onRetype: (type: DatasetColumnType) => void
  onDelete: () => void
}) {
  const { t } = useTranslation()
  if (!column) return null
  if (!editable) return <span className="font-semibold">{column.label}</span>
  return (
    <div className="flex flex-col gap-1">
      <span className="flex items-center gap-1 font-semibold">
        {column.label}
        <button
          type="button"
          data-testid={`dataset-delete-col-${column.slug}`}
          onClick={onDelete}
          className="text-gray-400 hover:text-red-600"
          title={t('dataset.deleteColumn')}
        >
          <X size={12} />
        </button>
      </span>
      <select
        data-testid={`dataset-coltype-${column.slug}`}
        value={column.type}
        onChange={(e) => onRetype(e.target.value as DatasetColumnType)}
        className="rounded border border-gray-200 bg-white px-1 py-0.5 text-xs font-normal"
      >
        {DATASET_COLUMN_TYPES.map((ty) => (
          <option key={ty} value={ty}>
            {t(`dataset.type.${ty}`)}
          </option>
        ))}
      </select>
    </div>
  )
}

// ── Ajout de colonne ─────────────────────────────────────────────────────────

function AddColumnControl({ onAdd }: { onAdd: (label: string, type: DatasetColumnType) => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [type, setType] = useState<DatasetColumnType>('text')
  if (!open)
    return (
      <button
        type="button"
        data-testid="dataset-add-col-btn"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900"
        title={t('dataset.addColumn')}
      >
        <Plus size={14} />
      </button>
    )
  return (
    <div className="flex flex-col gap-1">
      <input
        data-testid="dataset-new-col-label"
        autoFocus
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder={t('dataset.columnLabel')}
        className="rounded border border-gray-200 px-1 py-0.5 text-xs"
      />
      <select
        value={type}
        onChange={(e) => setType(e.target.value as DatasetColumnType)}
        className="rounded border border-gray-200 px-1 py-0.5 text-xs"
      >
        {DATASET_COLUMN_TYPES.map((ty) => (
          <option key={ty} value={ty}>
            {t(`dataset.type.${ty}`)}
          </option>
        ))}
      </select>
      <div className="flex gap-1">
        <button
          type="button"
          data-testid="dataset-new-col-confirm"
          disabled={!label.trim()}
          onClick={() => {
            onAdd(label.trim(), type)
            setLabel('')
            setType('text')
            setOpen(false)
          }}
          className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white disabled:opacity-40"
        >
          {t('dataset.add')}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="text-xs text-gray-500">
          {t('dataset.cancel')}
        </button>
      </div>
    </div>
  )
}

// ── Import CSV ───────────────────────────────────────────────────────────────

function ImportButton({ onFile }: { onFile: (text: string) => void }) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <>
      <button
        type="button"
        data-testid="dataset-import-btn"
        onClick={() => inputRef.current?.click()}
        className="inline-flex items-center gap-1 rounded border border-gray-200 px-2 py-1 text-xs hover:bg-gray-50"
      >
        <Upload size={14} /> {t('dataset.import')}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (!file) return
          void file.text().then((text) => onFile(text))
          e.target.value = ''
        }}
      />
    </>
  )
}

interface ParsedImport {
  csv: string
  columns: InferredColumn[]
  preview: string[][]
}

function makeImport(csv: string): ParsedImport {
  const parsed = parseCsv(csv, true)
  return { csv, columns: parsed.columns, preview: parsed.rows.slice(0, 5) }
}

function ImportPreview({
  state,
  setState,
  onCancel,
  onConfirm,
  pending,
}: {
  state: ParsedImport
  setState: (s: ParsedImport) => void
  onCancel: () => void
  onConfirm: (mode: 'replace' | 'append') => void
  pending: boolean
}) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'replace' | 'append'>('replace')
  const setColType = (i: number, type: DatasetColumnType) => {
    const columns = state.columns.map((c, idx) => (idx === i ? { ...c, type } : c))
    setState({ ...state, columns })
  }
  return (
    <div data-testid="dataset-import-preview" className="mt-3 rounded border border-blue-200 bg-blue-50 p-3">
      <div className="mb-2 text-sm font-medium">{t('dataset.importPreview')}</div>
      <div className="mb-2 flex flex-wrap gap-2">
        {state.columns.map((c, i) => (
          <div key={c.slug} className="flex flex-col rounded border border-gray-200 bg-white px-2 py-1">
            <span className="text-xs font-semibold">{c.label}</span>
            <select
              data-testid={`dataset-import-coltype-${c.slug}`}
              value={c.type}
              onChange={(e) => setColType(i, e.target.value as DatasetColumnType)}
              className="text-xs"
            >
              {DATASET_COLUMN_TYPES.map((ty) => (
                <option key={ty} value={ty}>
                  {t(`dataset.type.${ty}`)}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>
      <label className="mb-2 flex items-center gap-2 text-xs">
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as 'replace' | 'append')}
          className="rounded border border-gray-200 px-1 py-0.5"
        >
          <option value="replace">{t('dataset.modeReplace')}</option>
          <option value="append">{t('dataset.modeAppend')}</option>
        </select>
      </label>
      <div className="flex gap-2">
        <button
          type="button"
          data-testid="dataset-import-confirm"
          disabled={pending || state.columns.length === 0}
          onClick={() => onConfirm(mode)}
          className="rounded bg-blue-600 px-3 py-1 text-xs text-white disabled:opacity-40"
        >
          {t('dataset.import')}
        </button>
        <button type="button" onClick={onCancel} className="text-xs text-gray-600">
          {t('dataset.cancel')}
        </button>
      </div>
    </div>
  )
}

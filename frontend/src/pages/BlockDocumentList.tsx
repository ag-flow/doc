import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ExpandedState,
  type SortingState,
  type VisibilityState,
} from '@tanstack/react-table'
import {
  docsApi,
  type AllowedTypeOut,
  type DocumentOut,
  type FunctionalTypeRich,
  type DocPropValue,
} from '../lib/api'
import { Button } from '../components/ui/button'
import { AddDocumentDialog } from '../components/AddDocumentDialog'

interface TreeRow extends DocumentOut {
  subRows: TreeRow[]
}

function buildTree(docs: DocumentOut[]): TreeRow[] {
  const byId = new Map<string, TreeRow>(
    docs.map((d) => [d.doc_technical_key, { ...d, subRows: [] }]),
  )
  const roots: TreeRow[] = []
  for (const doc of byId.values()) {
    if (doc.parent_id && byId.has(doc.parent_id)) {
      byId.get(doc.parent_id)!.subRows.push(doc)
    } else {
      roots.push(doc)
    }
  }
  return roots
}

function pathPreservingFilter(
  docs: DocumentOut[],
  filters: Record<string, string>,
  values: Record<string, DocPropValue[]>,
): DocumentOut[] {
  if (Object.keys(filters).length === 0) return docs

  const matched = new Set(
    docs
      .filter((doc) => {
        const docVals = values[doc.doc_technical_key] ?? []
        return Object.entries(filters).every(([propSlug, valueSlug]) => {
          const pv = docVals.find((v) => v.prop_slug === propSlug)
          return pv?.allowed_value_slug === valueSlug
        })
      })
      .map((d) => d.doc_technical_key),
  )

  const byId = new Map(docs.map((d) => [d.doc_technical_key, d]))
  const visible = new Set(matched)

  for (const id of matched) {
    let cur: DocumentOut | undefined = byId.get(id)
    while (cur?.parent_id) {
      if (visible.has(cur.parent_id)) break
      visible.add(cur.parent_id)
      cur = byId.get(cur.parent_id)
    }
  }

  return docs.filter((d) => visible.has(d.doc_technical_key))
}

function ColorPill({ label, color }: { label: string; color: string | null }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
      style={
        color
          ? { backgroundColor: color, color: '#fff' }
          : { backgroundColor: '#e5e7eb', color: '#374151' }
      }
    >
      {label}
    </span>
  )
}

interface PropColDef {
  slug: string
  label: string
  type: string
  allowedValues: { slug: string; label: string; color: string | null }[]
}

export function BlockDocumentList() {
  const { t } = useTranslation()
  // Route /ws/:wsSlug/blocs/:blocSlug/documents
  const { wsSlug: ws, blocSlug: block } = useParams<{ wsSlug: string; blocSlug: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [treeMode, setTreeMode] = useState(true)
  const [expanded, setExpanded] = useState<ExpandedState>(true)
  const [sorting, setSorting] = useState<SortingState>([])
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({})
  const [showColMenu, setShowColMenu] = useState(false)
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [dialogParent, setDialogParent] = useState<string | null | undefined>(undefined)

  const { data: documents = [], isLoading } = useQuery<DocumentOut[]>({
    queryKey: ['block-documents', ws, block],
    queryFn: () => docsApi.getBlockDocuments(ws!, block!),
    enabled: Boolean(ws && block),
  })

  const { data: types = [] } = useQuery<FunctionalTypeRich[]>({
    queryKey: ['types-rich', ws],
    queryFn: () => docsApi.getTypesRich(ws!),
    enabled: Boolean(ws),
  })

  const { data: blockValues = {} } = useQuery<Record<string, DocPropValue[]>>({
    queryKey: ['block-values', ws, block],
    queryFn: () => docsApi.getBlockValues(ws!, block!),
    enabled: Boolean(ws && block),
  })

  const { data: rootAllowedTypes = [] } = useQuery<AllowedTypeOut[]>({
    queryKey: ['allowed-types', ws, block, 'root'],
    queryFn: () => docsApi.getAllowedTypes(ws!, block!),
    enabled: Boolean(ws && block),
  })

  const childTypesByParent = useMemo(() => {
    const map = new Map<string, FunctionalTypeRich[]>()
    for (const ft of types) {
      if (ft.parent_slug) {
        const arr = map.get(ft.parent_slug) ?? []
        arr.push(ft)
        map.set(ft.parent_slug, arr)
      }
    }
    return map
  }, [types])

  // Union des propriétés des types présents dans les docs du bloc
  const typeSlugSet = useMemo(
    () => new Set(documents.map((d) => d.functional_type_slug).filter(Boolean) as string[]),
    [documents],
  )

  const propColumns = useMemo<PropColDef[]>(() => {
    const seen = new Set<string>()
    const cols: PropColDef[] = []
    for (const ft of types) {
      if (!typeSlugSet.has(ft.slug)) continue
      for (const p of ft.properties ?? []) {
        if (!seen.has(p.slug)) {
          seen.add(p.slug)
          cols.push({
            slug: p.slug,
            label: p.label,
            type: p.type,
            allowedValues: p.allowed_values ?? [],
          })
        }
      }
    }
    return cols
  }, [types, typeSlugSet])

  const filteredDocs = useMemo(
    () => pathPreservingFilter(documents, filters, blockValues),
    [documents, filters, blockValues],
  )

  const data = useMemo<TreeRow[]>(
    () =>
      treeMode
        ? buildTree(filteredDocs)
        : filteredDocs.map((d) => ({ ...d, subRows: [] })),
    [filteredDocs, treeMode],
  )

  const columns = useMemo<ColumnDef<TreeRow>[]>(() => {
    const staticCols: ColumnDef<TreeRow>[] = [
      {
        accessorKey: 'title',
        header: t('documents.titleField'),
        cell: ({ row, getValue }) => (
          <div
            className="flex items-center gap-1"
            style={{ paddingLeft: treeMode ? `${row.depth * 16}px` : undefined }}
          >
            {treeMode && row.getCanExpand() ? (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  row.toggleExpanded()
                }}
                className="w-4 text-gray-500"
                data-testid={`expand-${row.original.doc_technical_key}`}
              >
                {row.getIsExpanded() ? '▾' : '▸'}
              </button>
            ) : (
              treeMode && <span className="w-4" />
            )}
            <span className="text-sm font-medium">{String(getValue())}</span>
          </div>
        ),
      },
      {
        accessorKey: 'functional_type_slug',
        header: t('documents.type'),
        cell: ({ getValue }) => (
          <span className="font-mono text-xs text-gray-500">{String(getValue() ?? '—')}</span>
        ),
      },
    ]

    const dynCols: ColumnDef<TreeRow>[] = propColumns.map((p) => ({
      id: `prop_${p.slug}`,
      header: p.label,
      enableSorting: false,
      cell: ({ row }) => {
        const docVals = blockValues[row.original.doc_technical_key] ?? []
        const pv = docVals.find((v) => v.prop_slug === p.slug)
        if (!pv) return <span className="text-gray-300">—</span>
        if (p.type === 'restricted_list') {
          if (!pv.allowed_value_slug) return <span className="text-gray-300">—</span>
          return (
            <ColorPill
              label={pv.allowed_value_label ?? pv.allowed_value_slug}
              color={pv.allowed_value_color ?? null}
            />
          )
        }
        return <span className="text-sm">{pv.value ?? '—'}</span>
      },
    }))

    const actionCol: ColumnDef<TreeRow> = {
      id: 'actions',
      header: '',
      enableSorting: false,
      cell: ({ row }) => {
        const docTypeSlug = row.original.functional_type_slug
        const children = docTypeSlug ? (childTypesByParent.get(docTypeSlug) ?? []) : []
        if (children.length === 0) return null
        const label = children.length === 1
          ? t('documents.addType', { type: children[0].label })
          : '+'
        return (
          <Button
            size="sm"
            variant="secondary"
            onClick={(e) => {
              e.stopPropagation()
              setDialogParent(row.original.doc_technical_key)
            }}
            data-testid={`add-child-${row.original.doc_technical_key}`}
          >
            {label}
          </Button>
        )
      },
    }

    return [...staticCols, ...dynCols, actionCol]
  }, [t, treeMode, propColumns, blockValues])

  const table = useReactTable({
    data,
    columns,
    state: { expanded, sorting, columnVisibility },
    onExpandedChange: setExpanded,
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getSubRows: (row) => row.subRows,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  function handleCreated(docId: string) {
    setDialogParent(undefined)
    void queryClient.invalidateQueries({ queryKey: ['block-documents', ws, block] })
    void queryClient.invalidateQueries({ queryKey: ['block-values', ws, block] })
    void navigate(`/ws/${ws}/blocs/${block}/documents/${docId}`)
  }

  if (isLoading) return <div className="p-8">{t('common.loading')}</div>

  return (
    <div className="p-8" data-testid="block-document-list">
      <div className="mb-4 flex items-center gap-3">
        <h1 className="mr-auto text-2xl font-semibold text-gray-900">{t('documents.title')}</h1>

        {/* Dropdown visibilité colonnes */}
        <div className="relative">
          <Button
            variant="secondary"
            onClick={() => setShowColMenu((v) => !v)}
            data-testid="columns-btn"
          >
            {t('documents.columns')}
          </Button>
          {showColMenu && (
            <div
              className="absolute right-0 z-10 mt-1 min-w-40 rounded border border-gray-200 bg-white p-3 shadow-lg"
              data-testid="columns-menu"
            >
              {table
                .getAllColumns()
                .filter((c) => c.id !== 'title' && c.id !== 'actions')
                .map((col) => (
                  <label key={col.id} className="mb-1 flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={col.getIsVisible()}
                      onChange={(e) => col.toggleVisibility(e.target.checked)}
                      data-testid={`col-toggle-${col.id}`}
                    />
                    {String(col.columnDef.header ?? col.id)}
                  </label>
                ))}
            </div>
          )}
        </div>

        <Button
          variant="secondary"
          onClick={() => setTreeMode((v) => !v)}
          data-testid="toggle-view-btn"
        >
          {treeMode ? t('documents.list_mode') : t('documents.tree_mode')}
        </Button>
        <Button onClick={() => setDialogParent(null)} data-testid="add-root-btn">
          {rootAllowedTypes.length === 1
            ? t('documents.addType', { type: rootAllowedTypes[0].label })
            : t('documents.add')}
        </Button>
      </div>

      {/* Filtres préservant le chemin pour chaque restricted_list visible */}
      {propColumns.filter((p) => p.type === 'restricted_list').length > 0 && (
        <div className="mb-4 flex flex-wrap gap-3" data-testid="filter-bar">
          {propColumns
            .filter((p) => p.type === 'restricted_list')
            .map((p) => (
              <div key={p.slug} className="flex items-center gap-1">
                <span className="text-sm text-gray-600">{p.label} :</span>
                <select
                  className="rounded border border-gray-300 px-2 py-1 text-sm"
                  value={filters[p.slug] ?? ''}
                  onChange={(e) =>
                    setFilters((prev) => {
                      const next = { ...prev }
                      if (e.target.value) {
                        next[p.slug] = e.target.value
                      } else {
                        delete next[p.slug]
                      }
                      return next
                    })
                  }
                  data-testid={`filter-${p.slug}`}
                >
                  <option value="">{t('documents.filter_all')}</option>
                  {p.allowedValues.map((av) => (
                    <option key={av.slug} value={av.slug}>
                      {av.label}
                    </option>
                  ))}
                </select>
              </div>
            ))}
        </div>
      )}

      {documents.length === 0 ? (
        <p className="text-gray-500">{t('documents.noDocuments')}</p>
      ) : filteredDocs.length === 0 ? (
        <p className="text-gray-500">{t('documents.noResults')}</p>
      ) : (
        <table className="w-full border-collapse" data-testid="documents-table">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b text-left text-sm font-medium text-gray-500">
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="cursor-pointer select-none pb-2 pr-4"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {{ asc: ' ↑', desc: ' ↓' }[header.column.getIsSorted() as string] ?? ''}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="cursor-pointer border-b hover:bg-gray-50"
                onClick={() =>
                  navigate(
                    `/ws/${ws}/blocs/${block}/documents/${row.original.doc_technical_key}`,
                  )
                }
                data-testid={`doc-row-${row.original.doc_technical_key}`}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="py-2 pr-4">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {dialogParent !== undefined && ws && block && (
        <AddDocumentDialog
          ws={ws}
          block={block}
          parentId={dialogParent ?? undefined}
          onCreated={handleCreated}
          onClose={() => setDialogParent(undefined)}
        />
      )}
    </div>
  )
}

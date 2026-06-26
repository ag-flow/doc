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
} from '@tanstack/react-table'
import { docsApi, type DocumentOut } from '../lib/api'
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

export function BlockDocumentList() {
  const { t } = useTranslation()
  const { ws, block } = useParams<{ ws: string; block: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [treeMode, setTreeMode] = useState(true)
  const [expanded, setExpanded] = useState<ExpandedState>(true)
  const [sorting, setSorting] = useState<SortingState>([])
  const [dialogParent, setDialogParent] = useState<string | null | undefined>(undefined)

  const { data: documents = [], isLoading } = useQuery<DocumentOut[]>({
    queryKey: ['block-documents', ws, block],
    queryFn: () => docsApi.getBlockDocuments(ws!, block!),
    enabled: Boolean(ws && block),
  })

  const data = useMemo<TreeRow[]>(
    () =>
      treeMode
        ? buildTree(documents)
        : documents.map((d) => ({ ...d, subRows: [] })),
    [documents, treeMode],
  )

  const columns = useMemo<ColumnDef<TreeRow>[]>(
    () => [
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
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <Button
            size="sm"
            variant="secondary"
            onClick={(e) => {
              e.stopPropagation()
              setDialogParent(row.original.doc_technical_key)
            }}
            data-testid={`add-child-${row.original.doc_technical_key}`}
          >
            +
          </Button>
        ),
      },
    ],
    [t, treeMode],
  )

  const table = useReactTable({
    data,
    columns,
    state: { expanded, sorting },
    onExpandedChange: setExpanded,
    onSortingChange: setSorting,
    getSubRows: (row) => row.subRows,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  function handleCreated(docId: string) {
    setDialogParent(undefined)
    void queryClient.invalidateQueries({ queryKey: ['block-documents', ws, block] })
    void navigate(`/workspaces/${ws}/blocks/${block}/documents/${docId}`)
  }

  if (isLoading) return <div className="p-8">{t('common.loading')}</div>

  return (
    <div className="p-8" data-testid="block-document-list">
      <div className="mb-6 flex items-center gap-3">
        <h1 className="mr-auto text-2xl font-semibold text-gray-900">{t('documents.title')}</h1>
        <Button
          variant="secondary"
          onClick={() => setTreeMode((v) => !v)}
          data-testid="toggle-view-btn"
        >
          {treeMode ? t('documents.list_mode') : t('documents.tree_mode')}
        </Button>
        <Button onClick={() => setDialogParent(null)} data-testid="add-root-btn">
          {t('documents.add')}
        </Button>
      </div>

      {documents.length === 0 ? (
        <p className="text-gray-500">{t('documents.noDocuments')}</p>
      ) : (
        <table className="w-full border-collapse" data-testid="documents-table">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b text-left text-sm font-medium text-gray-500">
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="cursor-pointer pb-2 pr-4 select-none"
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
                    `/workspaces/${ws}/blocks/${block}/documents/${row.original.doc_technical_key}`,
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

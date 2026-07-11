import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  useReactTable,
  type ColumnDef,
  type ExpandedState,
  type VisibilityState,
} from '@tanstack/react-table'
import {
  docsApi,
  type AllowedTypeOut,
  type BlockObjectsPage,
  type BlockTreeNode,
  type BlockTreePage,
  type DataBlockOut,
  type DocumentOut,
  type FunctionalTypeRich,
} from '../lib/api'
import { useQuerySpecState } from '../hooks/useQuerySpecState'
import { Trash2 } from 'lucide-react'
import { Button } from '../components/ui/button'
import { AddDocumentDialog } from '../components/AddDocumentDialog'
import { DeleteBlocDialog } from '../components/DeleteBlocDialog'
import { HeaderFilterPopover } from '../components/HeaderFilterPopover'

interface TreeRow {
  id: string
  title: string
  functional_type_slug: string | null
  subRows: TreeRow[]
  /** Renseigné en mode requête (query) : valeurs déjà aplaties par le serveur. */
  properties?: { prop_slug: string; value: string | null; allowed_value_slug: string | null }[]
}

/** Slug conventionnel de la propriété « statut » (une `restricted_list` par type).
 *  docflow ne réserve aucun concept de statut (spec 02_DATA_MODEL §143 : « le statut
 *  n'est pas un concept spécial ») ; on cible donc ce slug explicitement plutôt que
 *  « la première restricted_list », car un type peut en porter plusieurs (ex. `bug`
 *  a `severite` ET `statut`) — une heuristique générique choisirait la mauvaise. */
const STATUS_PROP_SLUG = 'statut'

/** Statut d'un nœud (slug de valeur autorisée), ou null si non renseigné/absent. */
function statusOf(node: BlockTreeNode): string | null {
  const pv = node.properties.find((p) => p.prop_slug === STATUS_PROP_SLUG)
  return pv?.allowed_value_slug ?? null
}

/** État d'expansion initial (TanStack `ExpandedState`) du mode browse arbre.
 *
 *  Règle : un parent démarre **déplié** seulement si ses enfants directs présentent
 *  des statuts **divergents** (≥ 2 valeurs distinctes) ; sinon il démarre **replié**
 *  (enfants homogènes, sans statut, ou parent d'un seul enfant). Un statut non
 *  renseigné ne crée pas de divergence — conforme au critère « collapsé si aucun
 *  statut divergent ». Seuls les nœuds dépliés figurent dans la carte (absent = replié). */
function computeDefaultExpanded(roots: BlockTreeNode[]): Record<string, boolean> {
  const state: Record<string, boolean> = {}
  const visit = (node: BlockTreeNode) => {
    if (node.children.length > 0) {
      const distinct = new Set(
        node.children.map(statusOf).filter((s): s is string => s !== null),
      )
      if (distinct.size >= 2) state[node.id] = true
      node.children.forEach(visit)
    }
  }
  roots.forEach(visit)
  return state
}

/** Mode browse arbre : convertit un nœud `list_block_tree` (récursif) en ligne de table. */
function treeNodeToRow(node: BlockTreeNode): TreeRow {
  return {
    id: node.id,
    title: node.title,
    functional_type_slug: node.functional_type_slug,
    subRows: node.children.map(treeNodeToRow),
    properties: node.properties,
  }
}

/** Mode browse liste (non arbre) : aplatit l'arbre en profondeur (parent puis
 *  descendants). Appliqué APRÈS le tri hiérarchique, donc l'ordre parent→enfants
 *  triés est préservé. */
function flattenRows(rows: TreeRow[]): TreeRow[] {
  const out: TreeRow[] = []
  const walk = (list: TreeRow[]) => {
    for (const r of list) {
      out.push({ ...r, subRows: [] })
      walk(r.subRows)
    }
  }
  walk(rows)
  return out
}

interface BrowseSort {
  key: string
  dir: 'asc' | 'desc'
}

/** Tri hiérarchique : ordonne chaque niveau (racines, puis récursivement les
 *  enfants dans chaque parent) par la clé/direction. Un enfant reste toujours
 *  sous son parent — on ne trie jamais à plat entre niveaux. Seul `title` est
 *  triable côté arbre (cohérent avec l'unique colonne triable de l'entête). */
function sortTreeRows(rows: TreeRow[], sort: BrowseSort): TreeRow[] {
  const cmp = (a: TreeRow, b: TreeRow): number => {
    const r = a.title.localeCompare(b.title)
    return sort.dir === 'asc' ? r : -r
  }
  const sortLevel = (list: TreeRow[]): TreeRow[] =>
    [...list].sort(cmp).map((r) => ({ ...r, subRows: sortLevel(r.subRows) }))
  return sortLevel(rows)
}

function flatRows(page: BlockObjectsPage): TreeRow[] {
  return page.objects.map((o) => ({
    id: o.id,
    title: o.title,
    functional_type_slug: o.functional_type_slug,
    subRows: [],
    properties: o.properties,
  }))
}

/** Valeur d'une propriété pour une ligne. Les deux modes (browse arbre, query)
 *  aplatissent désormais les valeurs directement sur la ligne (`properties`).
 *  La couleur d'une restricted_list se résout depuis les `allowed_values` du
 *  type (ni le mode browse ni le mode requête ne la retournent). */
function propValueFor(
  row: TreeRow,
  propSlug: string,
): { value: string | null; allowedSlug: string | null } | null {
  const pv = (row.properties ?? []).find((p) => p.prop_slug === propSlug)
  return pv ? { value: pv.value, allowedSlug: pv.allowed_value_slug } : null
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

/** Plafond serveur de `list_block_tree` (racines par page, mode browse). */
const BROWSE_PAGE_SIZE = 100

export function BlockDocumentList() {
  const { t } = useTranslation()
  // Route /ws/:wsSlug/blocs/:blocSlug/documents
  const { wsSlug: ws, blocSlug: block } = useParams<{ wsSlug: string; blocSlug: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [treeMode, setTreeMode] = useState(true)
  // Vide au départ ; peuplé par `computeDefaultExpanded` dès que l'arbre charge.
  const [expanded, setExpanded] = useState<ExpandedState>({})
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({})
  const [showColMenu, setShowColMenu] = useState(false)
  const [dialogParent, setDialogParent] = useState<string | null | undefined>(undefined)
  const [showDeleteBloc, setShowDeleteBloc] = useState(false)

  const { spec, mode, setFilter, toggleSort, setProjection, setPage, reset } = useQuerySpecState()

  // Pagination + tri hiérarchique du mode browse (racines, ≤100/page).
  const [browsePage, setBrowsePage] = useState(1)
  const [browseSort, setBrowseSort] = useState<BrowseSort | null>(null)
  useEffect(() => {
    setBrowsePage(1)
    setBrowseSort(null)
  }, [ws, block])

  // Clic d'entête en mode browse : cycle asc → desc → aucun, appliqué à l'arbre
  // (ne bascule pas en mode requête, contrairement à `toggleSort` du QuerySpec).
  function toggleBrowseSort(key: string) {
    setBrowseSort((prev) =>
      prev?.key !== key
        ? { key, dir: 'asc' }
        : prev.dir === 'asc'
          ? { key, dir: 'desc' }
          : null,
    )
  }

  const { data: documents = [], isLoading } = useQuery<DocumentOut[]>({
    queryKey: ['block-documents', ws, block],
    queryFn: () => docsApi.getBlockDocuments(ws!, block!),
    enabled: Boolean(ws && block),
  })

  // Métadonnées des blocs (cache partagé avec l'écran Blocs) pour le libellé.
  const { data: blocs = [] } = useQuery<DataBlockOut[]>({
    queryKey: ['blocs', ws],
    queryFn: () => docsApi.getBlocks(ws!),
    enabled: Boolean(ws),
  })
  const blocLabel = blocs.find((b) => b.slug === block)?.label ?? block ?? ''

  function handleBlocDeleted() {
    setShowDeleteBloc(false)
    void queryClient.invalidateQueries({ queryKey: ['blocs', ws] })
    void navigate(`/ws/${ws}/blocs`)
  }

  const { data: types = [] } = useQuery<FunctionalTypeRich[]>({
    queryKey: ['types-rich', ws],
    queryFn: () => docsApi.getTypesRich(ws!),
    enabled: Boolean(ws),
  })

  // Mode browse : racines paginées + sous-arbres + valeurs (list_block_tree).
  const { data: treePage } = useQuery<BlockTreePage>({
    queryKey: ['block-tree', ws, block, browsePage],
    queryFn: () => docsApi.getBlockTree(ws!, block!, browsePage, BROWSE_PAGE_SIZE),
    enabled: Boolean(ws && block) && mode === 'browse',
    placeholderData: keepPreviousData,
  })

  // Collapse par défaut : recalcule l'état d'expansion à chaque (re)chargement de
  // l'arbre (changement de page/bloc, invalidation). Les toggles manuels de
  // l'utilisateur tiennent jusqu'au prochain rechargement.
  useEffect(() => {
    if (treePage) setExpanded(computeDefaultExpanded(treePage.roots))
  }, [treePage])

  const { data: rootAllowedTypes = [] } = useQuery<AllowedTypeOut[]>({
    queryKey: ['allowed-types', ws, block, 'root'],
    queryFn: () => docsApi.getAllowedTypes(ws!, block!),
    enabled: Boolean(ws && block),
  })

  // Mode requête : dès qu'un filtre/tri est actif, bascule automatique vers
  // une liste plate paginée serveur (≤100 lignes) pilotée par `spec`.
  const { data: queryPage, isFetching: queryFetching } = useQuery<BlockObjectsPage>({
    queryKey: ['block-query', ws, block, spec],
    queryFn: () => docsApi.queryBlockDocuments(ws!, block!, spec),
    enabled: Boolean(ws && block) && mode === 'query',
    placeholderData: keepPreviousData,
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

  // Lookup id de colonne (`prop_<slug>`) → définition, pour brancher le popover de filtre.
  const propColById = useMemo(
    () => new Map(propColumns.map((p) => [`prop_${p.slug}`, p])),
    [propColumns],
  )

  // Projection dérivée du sélecteur de colonnes : null si toutes les colonnes de
  // propriété sont visibles (le serveur remonte tout), sinon la liste des slugs
  // visibles. En mode requête, les colonnes masquées ne sont pas demandées.
  const projection = useMemo<string[] | null>(() => {
    const anyHidden = propColumns.some((p) => columnVisibility[`prop_${p.slug}`] === false)
    if (!anyHidden) return null
    return propColumns
      .filter((p) => columnVisibility[`prop_${p.slug}`] !== false)
      .map((p) => p.slug)
  }, [propColumns, columnVisibility])

  useEffect(() => setProjection(projection), [projection, setProjection])

  const rows = useMemo<TreeRow[]>(() => {
    if (mode === 'query') return queryPage ? flatRows(queryPage) : []
    if (!treePage) return []
    const treeRows = treePage.roots.map(treeNodeToRow)
    const sorted = browseSort ? sortTreeRows(treeRows, browseSort) : treeRows
    return treeMode ? sorted : flattenRows(sorted)
  }, [mode, queryPage, treeMode, treePage, browseSort])

  // Clé de tri QuerySpec d'une colonne, ou null si non triable dans le mode courant.
  // `title` est triable dans les deux modes ; les colonnes de propriété ne le sont
  // qu'en mode requête (le tri arbre reste title-only, cf. feature browse).
  function headerSortKey(columnId: string): string | null {
    if (columnId === 'title') return 'title'
    if (mode === 'query' && columnId.startsWith('prop_')) return columnId.slice('prop_'.length)
    return null
  }

  // Direction + rang (multi-clé) d'une colonne. Browse = tri arbre client
  // (`browseSort`, title uniquement) ; query = tri serveur (`spec.sort`).
  function sortStateFor(key: string): { dir: 'asc' | 'desc'; index: number } | null {
    if (mode === 'browse') {
      return browseSort?.key === key ? { dir: browseSort.dir, index: -1 } : null
    }
    const index = spec.sort.findIndex((s) => s.key === key)
    return index >= 0 ? { dir: spec.sort[index].dir, index } : null
  }

  const columns = useMemo<ColumnDef<TreeRow>[]>(() => {
    const staticCols: ColumnDef<TreeRow>[] = [
      {
        accessorKey: 'title',
        header: t('documents.titleField'),
        cell: ({ row, getValue }) => (
          <div
            className="flex items-center gap-1"
            style={{ paddingLeft: mode === 'browse' && treeMode ? `${row.depth * 16}px` : undefined }}
          >
            {mode === 'browse' && treeMode && row.getCanExpand() ? (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  row.toggleExpanded()
                }}
                className="w-4 text-gray-500"
                data-testid={`expand-${row.original.id}`}
              >
                {row.getIsExpanded() ? '▾' : '▸'}
              </button>
            ) : (
              mode === 'browse' && treeMode && <span className="w-4" />
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
      cell: ({ row }) => {
        const pv = propValueFor(row.original, p.slug)
        if (!pv || (pv.value === null && !pv.allowedSlug)) return <span className="text-gray-300">—</span>
        if (p.type === 'restricted_list') {
          if (!pv.allowedSlug) return <span className="text-gray-300">—</span>
          const av = p.allowedValues.find((a) => a.slug === pv.allowedSlug)
          return <ColorPill label={av?.label ?? pv.allowedSlug} color={av?.color ?? null} />
        }
        return <span className="text-sm">{pv.value ?? '—'}</span>
      },
    }))

    const actionCol: ColumnDef<TreeRow> = {
      id: 'actions',
      header: '',
      cell: ({ row }) => {
        const docId = row.original.id
        const docTypeSlug = row.original.functional_type_slug
        const docChildren = docTypeSlug ? (childTypesByParent.get(docTypeSlug) ?? []) : []
        const docPath = `/ws/${ws}/blocs/${block}/documents/${docId}`
        const addLabel = docChildren.length === 1
          ? t('documents.addType', { type: docChildren[0].label })
          : '+'
        return (
          <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
            <a
              href={docPath}
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 hover:text-gray-700 text-sm"
              title={t('documents.openNewTab')}
              data-testid={`open-newtab-${docId}`}
            >
              ↗
            </a>
            {docChildren.length > 0 && (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setDialogParent(docId)}
                data-testid={`add-child-${docId}`}
              >
                {addLabel}
              </Button>
            )}
          </div>
        )
      },
    }

    return [...staticCols, ...dynCols, actionCol]
  }, [t, mode, treeMode, propColumns, childTypesByParent, ws, block])

  const table = useReactTable({
    data: rows,
    columns,
    state: { expanded, columnVisibility },
    onExpandedChange: setExpanded,
    onColumnVisibilityChange: setColumnVisibility,
    getSubRows: (row) => row.subRows,
    // Clé de ligne = id du document → l'état d'expansion (computeDefaultExpanded)
    // référence des ids stables plutôt que des chemins d'index TanStack.
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
  })

  function handleCreated(docId: string) {
    setDialogParent(undefined)
    void queryClient.invalidateQueries({ queryKey: ['block-documents', ws, block] })
    void queryClient.invalidateQueries({ queryKey: ['block-tree', ws, block] })
    void navigate(`/ws/${ws}/blocs/${block}/documents/${docId}`)
  }

  if (isLoading) return <div className="p-8">{t('common.loading')}</div>

  const isEmpty =
    mode === 'query' ? (queryPage?.objects.length ?? 0) === 0 : (treePage?.roots.length ?? 0) === 0

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

        {mode === 'browse' && (
          <Button
            variant="secondary"
            onClick={() => setTreeMode((v) => !v)}
            data-testid="toggle-view-btn"
          >
            {treeMode ? t('documents.list_mode') : t('documents.tree_mode')}
          </Button>
        )}
        <Button onClick={() => setDialogParent(null)} data-testid="add-root-btn">
          {rootAllowedTypes.length === 1
            ? t('documents.addType', { type: rootAllowedTypes[0].label })
            : t('documents.add')}
        </Button>
        <Button
          variant="secondary"
          onClick={() => setShowDeleteBloc(true)}
          className="text-red-600 hover:bg-red-50"
          data-testid="delete-current-bloc-btn"
        >
          <Trash2 size={14} className="mr-1" />
          {t('blocs.deleteTitle')}
        </Button>
      </div>

      {/* Pagination en haut, mode browse : racines paginées (list_block_tree, ≤100/page). */}
      {mode === 'browse' && (
        <div className="mb-4 flex items-center gap-3 text-sm text-gray-600" data-testid="browse-pagination">
          <Button
            variant="secondary"
            size="sm"
            disabled={browsePage <= 1}
            onClick={() => setBrowsePage((p) => p - 1)}
            data-testid="browse-page-prev"
          >
            {t('documents.prev')}
          </Button>
          <span data-testid="browse-page-indicator">
            {treePage
              ? t('documents.pageIndicator', { page: treePage.page, total: treePage.total })
              : t('common.loading')}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={!treePage?.has_next}
            onClick={() => setBrowsePage((p) => p + 1)}
            data-testid="browse-page-next"
          >
            {t('documents.next')}
          </Button>
        </div>
      )}

      {/* Pagination en haut, mode requête : liste plate paginée serveur (≤100/page). */}
      {mode === 'query' && (
        <div className="mb-4 flex items-center gap-3 text-sm text-gray-600" data-testid="query-pagination">
          <Button
            variant="secondary"
            size="sm"
            disabled={spec.page <= 1}
            onClick={() => setPage(spec.page - 1)}
            data-testid="query-page-prev"
          >
            {t('documents.prev')}
          </Button>
          <span data-testid="query-page-indicator">
            {queryPage
              ? t('documents.pageIndicator', { page: queryPage.page, total: queryPage.total })
              : t('common.loading')}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={!queryPage?.has_next}
            onClick={() => setPage(spec.page + 1)}
            data-testid="query-page-next"
          >
            {t('documents.next')}
          </Button>
          <Button variant="secondary" size="sm" onClick={reset} data-testid="query-clear-btn">
            {t('documents.clearQuery')}
          </Button>
        </div>
      )}

      {isEmpty ? (
        <p className="text-gray-500">
          {mode === 'query' ? t('documents.noResults') : t('documents.noDocuments')}
        </p>
      ) : (
        <table className="w-full border-collapse" data-testid="documents-table">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b text-left text-sm font-medium text-gray-500">
                {hg.headers.map((header) => {
                  const sortKey = headerSortKey(header.column.id)
                  const sortState = sortKey ? sortStateFor(sortKey) : null
                  // Le rang n'est affiché que sur un tri multi-clé (mode requête).
                  const showRank = mode === 'query' && spec.sort.length > 1 && sortState
                  const propCol = propColById.get(header.column.id)
                  return (
                    <th
                      key={header.id}
                      className={sortKey ? 'cursor-pointer select-none pb-2 pr-4' : 'pb-2 pr-4'}
                      onClick={
                        sortKey
                          ? (e) =>
                              mode === 'browse'
                                ? toggleBrowseSort(sortKey)
                                : toggleSort(sortKey, e.shiftKey)
                          : undefined
                      }
                      data-testid={sortKey ? `sort-header-${sortKey}` : undefined}
                    >
                      <span className="inline-flex items-center gap-1">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {sortState && (
                          <span className="text-xs">
                            {sortState.dir === 'asc' ? '↑' : '↓'}
                            {showRank ? <sup>{sortState.index + 1}</sup> : null}
                          </span>
                        )}
                        {propCol && (
                          <HeaderFilterPopover
                            column={propCol}
                            clause={spec.filters.find((f) => f.prop === propCol.slug) ?? null}
                            onChange={(clause) => setFilter(propCol.slug, clause)}
                          />
                        )}
                      </span>
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody className={queryFetching ? 'opacity-60' : undefined}>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="cursor-pointer border-b hover:bg-gray-50"
                onClick={() => navigate(`/ws/${ws}/blocs/${block}/documents/${row.original.id}`)}
                data-testid={`doc-row-${row.original.id}`}
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

      {showDeleteBloc && ws && block && (
        <DeleteBlocDialog
          wsSlug={ws}
          blockSlug={block}
          blockLabel={blocLabel}
          onClose={() => setShowDeleteBloc(false)}
          onDeleted={handleBlocDeleted}
        />
      )}
    </div>
  )
}

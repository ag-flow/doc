import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  useQuery,
  useInfiniteQuery,
  useQueryClient,
  useMutation,
  keepPreviousData,
} from '@tanstack/react-query'
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
  prefsApi,
  viewsApi,
  type AllowedTypeOut,
  type BlockObjectsPage,
  type BlockTreeNode,
  type BlockTreePage,
  type DataBlockOut,
  type FunctionalTypeRich,
  type PropertyDefRich,
  type ViewOut,
} from '../lib/api'
import { useQuerySpecState } from '../hooks/useQuerySpecState'
import { readUrlState, writeUrlState } from '../lib/querySpecUrl'
import { relativeDate } from '../lib/relativeDate'
import { labelToSlug } from '../lib/slug'
import { ArrowDown, ArrowUp, ArrowSquareOut, Plus, Trash } from '@phosphor-icons/react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { SectionHead } from '../components/SectionHead'
import { ActiveFilterBar } from '../components/ActiveFilterBar'
import { EmptyState, TableSkeleton } from '../components/ui/states'
import { ReparentDialog } from '../components/ReparentDialog'
import { AddDocumentDialog } from '../components/AddDocumentDialog'
import { DeleteBlocDialog } from '../components/DeleteBlocDialog'
import { HeaderFilterPopover } from '../components/HeaderFilterPopover'
import { InlinePropertyCell } from '../components/InlinePropertyCell'

interface TreeRow {
  id: string
  title: string
  functional_type_slug: string | null
  updated_at?: string | null
  updated_by?: string | null
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
    updated_at: node.updated_at,
    updated_by: node.updated_by,
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

function flatRows(page: BlockObjectsPage): TreeRow[] {
  return page.objects.map((o) => ({
    id: o.id,
    title: o.title,
    functional_type_slug: o.functional_type_slug,
    updated_at: o.updated_at,
    updated_by: o.updated_by,
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

interface PropColDef {
  slug: string
  label: string
  type: string
  allowedValues: { slug: string; label: string; color: string | null }[]
}

/** Tailles de page proposées à l'utilisateur (mémorisée en préférence). */
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const
const DEFAULT_PAGE_SIZE = 25
const PAGE_SIZE_PREF = 'doc-page-size'

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

  // ── Sélection de colonnes : mémorisée PAR UTILISATEUR et PAR BLOC ────────
  // Préférence serveur (elle suit le compte d'un poste à l'autre), hydratée à
  // l'entrée du bloc ; chaque changement est poussé. On n'écrit pas avant
  // l'hydratation, sinon l'état initial vide écraserait la préférence.
  const colsPrefKey = `doc-columns:${ws}:${block}`
  const colsHydrated = useRef(false)
  useEffect(() => {
    colsHydrated.current = false
    setColumnVisibility({})
    let cancelled = false
    prefsApi.get<VisibilityState>(colsPrefKey)
      .then((res) => {
        if (cancelled) return
        if (res.value) setColumnVisibility(res.value)
        colsHydrated.current = true
      })
      .catch(() => { if (!cancelled) colsHydrated.current = true })
    return () => { cancelled = true }
  }, [colsPrefKey])

  function handleColumnVisibilityChange(updater: React.SetStateAction<VisibilityState>) {
    setColumnVisibility((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      if (colsHydrated.current) {
        // Toutes visibles = retour au défaut : la préférence s'efface.
        const anyHidden = Object.values(next).some((v) => v === false)
        void prefsApi.set(colsPrefKey, anyHidden ? next : null).catch(() => {})
      }
      return next
    })
  }
  // ── Taille de page : choix utilisateur mémorisé (préférence serveur) ──────
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE)
  useEffect(() => {
    let cancelled = false
    prefsApi.get<number>(PAGE_SIZE_PREF)
      .then((res) => {
        if (!cancelled && res.value && (PAGE_SIZE_OPTIONS as readonly number[]).includes(res.value))
          setPageSize(res.value)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])
  function changePageSize(size: number) {
    setPageSize(size)
    void prefsApi.set(PAGE_SIZE_PREF, size).catch(() => {})
  }

  const [showColMenu, setShowColMenu] = useState(false)
  const [dialogParent, setDialogParent] = useState<string | null | undefined>(undefined)
  // Drag & drop de re-parentage : doc glissé + destination (null = racine)
  const [reparentDrop, setReparentDrop] = useState<
    { doc: { id: string; title: string; type: string | null }; target: string | null } | null
  >(null)
  const [showDeleteBloc, setShowDeleteBloc] = useState(false)

  const { spec, mode, setFilter, toggleSort, setProjection, loadSpec, reset } =
    useQuerySpecState()

  // Tri hiérarchique du mode browse (la pagination est gérée par useInfiniteQuery).
  const [browseSort, setBrowseSort] = useState<BrowseSort | null>(null)

  // ── Tri et filtres dans l'URL ────────────────────────────────────────────
  // L'URL est la forme partageable de l'état : on l'hydrate UNE fois par bloc
  // (sinon l'écriture ci-dessous relancerait l'hydratation en boucle), puis on
  // l'écrit à chaque changement d'état.
  const [searchParams, setSearchParams] = useSearchParams()
  const hydratedFor = useRef<string | null>(null)

  useEffect(() => {
    const routeKey = `${ws}/${block}`
    if (hydratedFor.current === routeKey) return
    hydratedFor.current = routeKey

    // Les params viennent du router (et non de window.location) : c'est la même
    // source en navigateur, et la seule qui existe sous MemoryRouter (tests).
    const url = readUrlState(searchParams)
    setTreeMode(url.treeMode)
    if (url.spec.filters.length > 0) {
      // Filtres présents → mode requête : le tri appartient au QuerySpec.
      loadSpec({
        filters: url.spec.filters,
        sort: url.spec.sort,
        projection: null,
        page: 1,
        page_size: DEFAULT_PAGE_SIZE,
      })
      setBrowseSort(null)
    } else {
      // Sans filtre on reste en navigation : le tri est celui de l'arbre.
      reset()
      setBrowseSort(url.spec.sort[0] ? { key: url.spec.sort[0].key, dir: url.spec.sort[0].dir } : null)
    }
    // `searchParams` volontairement hors dépendances : l'hydratation est un
    // événement d'entrée de route, pas un abonnement aux changements d'URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws, block, loadSpec, reset])

  useEffect(() => {
    if (hydratedFor.current !== `${ws}/${block}`) return
    const next = writeUrlState({
      spec: {
        filters: spec.filters,
        sort: mode === 'query' ? spec.sort : browseSort ? [browseSort] : [],
        page: 1, // « Charger plus » : la page n'est plus dans l'URL (accumulation).
      },
      treeMode,
    })
    // Remplacement (et non push) : trier ne doit pas empiler des entrées
    // d'historique que le bouton « retour » devrait dépiler une par une.
    if (next.toString() !== searchParams.toString()) setSearchParams(next, { replace: true })
  }, [spec, mode, browseSort, treeMode, ws, block, searchParams, setSearchParams])

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

  // Types présents dans le bloc (léger) : sert à dériver les colonnes de
  // propriétés SANS charger tous les documents — préalable à la pagination.
  const { data: presentTypeSlugs = [], isLoading } = useQuery<string[]>({
    queryKey: ['block-type-slugs', ws, block],
    queryFn: () => docsApi.getPresentTypeSlugs(ws!, block!),
    enabled: Boolean(ws && block),
  })

  // Métadonnées des blocs (cache partagé avec l'écran Blocs) pour le libellé.
  const { data: blocs = [] } = useQuery<DataBlockOut[]>({
    queryKey: ['blocs', ws],
    queryFn: () => docsApi.getBlocks(ws!),
    enabled: Boolean(ws),
  })
  const currentBloc = blocs.find((b) => b.slug === block) ?? null
  const blocLabel = currentBloc?.label ?? block ?? ''

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

  // Mode browse : racines paginées + sous-arbres + valeurs, ACCUMULÉES par
  // « Charger plus » (useInfiniteQuery). Changer le tri ou la taille de page
  // change la clé → repart de la page 1.
  // Le tri browse est appliqué CÔTÉ SERVEUR (racines + enfants), donc inclus dans
  // la clé : le changer repart de la page 1 et réordonne tout le jeu, pas seulement
  // les pages déjà chargées. Seule la colonne « Modifié » et le titre sont triables.
  const browseSortKey: 'title' | 'updated_at' =
    browseSort?.key === 'updated_at' ? 'updated_at' : 'title'
  const browseSortDir: 'asc' | 'desc' = browseSort?.dir ?? 'asc'
  const browseInfinite = useInfiniteQuery<BlockTreePage>({
    queryKey: ['block-tree', ws, block, pageSize, browseSortKey, browseSortDir],
    queryFn: ({ pageParam }) =>
      docsApi.getBlockTree(ws!, block!, pageParam as number, pageSize, browseSortKey, browseSortDir),
    enabled: Boolean(ws && block) && mode === 'browse',
    initialPageParam: 1,
    getNextPageParam: (last) => (last.has_next ? last.page + 1 : undefined),
    placeholderData: keepPreviousData,
  })
  const browseRoots = useMemo(
    () => (browseInfinite.data?.pages ?? []).flatMap((p) => p.roots),
    [browseInfinite.data],
  )
  const browseTotal = browseInfinite.data?.pages[0]?.total ?? 0

  // Collapse par défaut : recalculé quand les racines chargées changent (bloc,
  // tri, « Charger plus », invalidation). Les toggles manuels tiennent jusque-là.
  useEffect(() => {
    if (browseRoots.length > 0) setExpanded(computeDefaultExpanded(browseRoots))
  }, [browseRoots])

  // ── Vues enregistrées ────────────────────────────────────────────────────
  const [showSaveView, setShowSaveView] = useState(false)
  const { data: views = [] } = useQuery<ViewOut[]>({
    queryKey: ['views', ws],
    queryFn: () => viewsApi.list(ws!),
    enabled: Boolean(ws),
    staleTime: 60_000,
  })
  // Les vues du bloc courant, plus celles qui ne visent aucun bloc en particulier.
  const blocViews = useMemo(
    () => views.filter((v) => v.bloc_ref === null || v.bloc_ref === currentBloc?.id),
    [views, currentBloc?.id],
  )

  const saveViewMutation = useMutation({
    mutationFn: (label: string) =>
      viewsApi.create(ws!, {
        slug: labelToSlug(label),
        label,
        layout: 'table',
        filter: spec.filters,
        sort: mode === 'query' ? spec.sort : browseSort ? [browseSort] : [],
        columns: Object.entries(columnVisibility)
          .filter(([, visible]) => visible === false)
          .map(([id]) => id),
        bloc_ref: currentBloc?.id ?? null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['views', ws] })
      setShowSaveView(false)
    },
  })

  const deleteViewMutation = useMutation({
    mutationFn: (slug: string) => viewsApi.remove(ws!, slug),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['views', ws] }) },
  })

  /** Rappelle une vue : filtres + tri. Sans filtre, la vue ne fait que trier
   *  l'arbre — on ne bascule pas en mode requête pour rien. */
  function applyView(view: ViewOut) {
    if (view.filter.length > 0) {
      loadSpec({
        filters: view.filter,
        sort: view.sort,
        projection: null,
        page: 1,
        page_size: DEFAULT_PAGE_SIZE,
      })
      setBrowseSort(null)
    } else {
      reset()
      setBrowseSort(view.sort[0] ? { key: view.sort[0].key, dir: view.sort[0].dir } : null)
    }
  }

  const { data: rootAllowedTypes = [] } = useQuery<AllowedTypeOut[]>({
    queryKey: ['allowed-types', ws, block, 'root'],
    queryFn: () => docsApi.getAllowedTypes(ws!, block!),
    enabled: Boolean(ws && block),
  })

  // Mode requête (filtre/tri actif) : liste plate paginée serveur, ACCUMULÉE
  // par « Charger plus ». La clé exclut la page (gérée par l'infinite query) ;
  // filtres/tri/projection/taille de page la font repartir de la page 1.
  const querySpecKey = { filters: spec.filters, sort: spec.sort, projection: spec.projection }
  const queryInfinite = useInfiniteQuery<BlockObjectsPage>({
    queryKey: ['block-query', ws, block, querySpecKey, pageSize],
    queryFn: ({ pageParam }) =>
      docsApi.queryBlockDocuments(ws!, block!, {
        ...spec,
        page: pageParam as number,
        page_size: pageSize,
      }),
    enabled: Boolean(ws && block) && mode === 'query',
    initialPageParam: 1,
    getNextPageParam: (last) => (last.has_next ? last.page + 1 : undefined),
    placeholderData: keepPreviousData,
  })
  const queryFetching = queryInfinite.isFetching
  const queryTotal = queryInfinite.data?.pages[0]?.total ?? 0
  const queryEmpty = (queryInfinite.data?.pages[0]?.objects.length ?? 0) === 0

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

  // Union des propriétés des types présents dans le bloc (endpoint léger).
  const typeSlugSet = useMemo(() => new Set(presentTypeSlugs), [presentTypeSlugs])

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

  // Index type → (prop_slug → def) : donne, par ligne, les valeurs autorisées
  // scopées au type du document et son `behavior` (édition inline).
  const typePropIndex = useMemo(() => {
    const m = new Map<string, Map<string, PropertyDefRich>>()
    for (const ty of types) {
      const inner = new Map<string, PropertyDefRich>()
      for (const p of ty.properties ?? []) inner.set(p.slug, p)
      m.set(ty.slug, inner)
    }
    return m
  }, [types])

  // Après une édition inline, rafraîchir les données de la table (les deux modes).
  const handleValueSaved = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['block-tree', ws, block] })
    void queryClient.invalidateQueries({ queryKey: ['block-query', ws, block] })
  }, [queryClient, ws, block])

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
    if (mode === 'query') {
      return (queryInfinite.data?.pages ?? []).flatMap((p) => flatRows(p))
    }
    // L'ordre vient du serveur (racines + enfants triés par la clé browse) ;
    // en mode liste plate on aplatit sans réordonner.
    const treeRows = browseRoots.map(treeNodeToRow)
    return treeMode ? treeRows : flattenRows(treeRows)
  }, [mode, queryInfinite.data, browseRoots, treeMode])

  // Clé de tri d'une colonne, ou null si non triable dans le mode courant.
  // `title` et `updated_at` (colonne « Modifié ») sont triables dans les deux modes
  // (serveur) ; les colonnes de propriété ne le sont qu'en mode requête.
  function headerSortKey(columnId: string): string | null {
    if (columnId === 'title') return 'title'
    if (columnId === 'updated') return 'updated_at'
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
      {
        id: 'updated',
        accessorKey: 'updated_at',
        header: t('documents.modified', 'Modifié'),
        cell: ({ row }) => {
          const at = row.original.updated_at
          if (!at) return <span className="text-ink/[0.4]">—</span>
          return (
            <span className="text-[12px] text-ink/[0.55]"
              data-testid={`modified-${row.original.id}`}>
              {relativeDate(at)}
              {row.original.updated_by && (
                <span className="text-ink/[0.45]"> par {row.original.updated_by}</span>
              )}
            </span>
          )
        },
      },
    ]

    const dynCols: ColumnDef<TreeRow>[] = propColumns.map((p) => ({
      id: `prop_${p.slug}`,
      header: p.label,
      cell: ({ row }) => {
        const pv = propValueFor(row.original, p.slug)
        const docType = row.original.functional_type_slug
        // Édition inline scopée au type du document : une propriété n'est
        // éditable que si le type du doc la définit et qu'elle n'est pas auto.
        const def = docType ? typePropIndex.get(docType)?.get(p.slug) : undefined
        return (
          <InlinePropertyCell
            ws={ws!}
            docId={row.original.id}
            propSlug={p.slug}
            propType={p.type}
            value={pv?.value ?? null}
            allowedSlug={pv?.allowedSlug ?? null}
            allowedValues={def?.allowed_values ?? []}
            editable={Boolean(def) && !def!.behavior}
            onSaved={handleValueSaved}
          />
        )
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
              className="text-ink/[0.4] hover:text-accent-700"
              title={t('documents.openNewTab')}
              data-testid={`open-newtab-${docId}`}
            >
              <ArrowSquareOut size={14} weight="duotone" />
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
  }, [t, mode, treeMode, propColumns, typePropIndex, handleValueSaved, childTypesByParent, ws, block])

  const table = useReactTable({
    data: rows,
    columns,
    state: { expanded, columnVisibility },
    onExpandedChange: setExpanded,
    onColumnVisibilityChange: handleColumnVisibilityChange,
    getSubRows: (row) => row.subRows,
    // Clé de ligne = id du document → l'état d'expansion (computeDefaultExpanded)
    // référence des ids stables plutôt que des chemins d'index TanStack.
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
  })

  function handleCreated(docId: string) {
    setDialogParent(undefined)
    // Un nouveau document peut introduire un nouveau type → rafraîchir aussi les colonnes.
    void queryClient.invalidateQueries({ queryKey: ['block-type-slugs', ws, block] })
    void queryClient.invalidateQueries({ queryKey: ['block-tree', ws, block] })
    void queryClient.invalidateQueries({ queryKey: ['block-query', ws, block] })
    void navigate(`/ws/${ws}/blocs/${block}/documents/${docId}`)
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1200px] px-6 pt-11">
        <TableSkeleton rows={8} columns={4} />
      </div>
    )
  }

  const isEmpty = mode === 'query' ? queryEmpty : browseRoots.length === 0

  const propLabelOf = (prop: string) =>
    propColumns.find((p) => p.slug === prop)?.label ?? prop
  const propValueLabelOf = (prop: string, value: string) =>
    propColumns.find((p) => p.slug === prop)?.allowedValues.find((av) => av.slug === value)?.label
    ?? value

  return (
    <div className="mx-auto max-w-[1200px] px-6 pt-11 pb-24" data-testid="block-document-list">
      <SectionHead kicker={ws ?? ''} title={blocLabel || t('documents.title')}>
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
              className="dialog elev-lg absolute right-0 z-20 mt-1 min-w-40 gap-1 p-3"
              data-testid="columns-menu"
            >
              {table
                .getAllColumns()
                .filter((c) => c.id !== 'title' && c.id !== 'actions')
                .map((col) => (
                  <label key={col.id} className="flex items-center gap-2 text-[14px]">
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
          <Plus size={16} weight="duotone" />
          {rootAllowedTypes.length === 1
            ? t('documents.addType', { type: rootAllowedTypes[0].label })
            : t('documents.add')}
        </Button>
        <Button
          variant="secondary"
          onClick={() => setShowDeleteBloc(true)}
          className="text-accent-2-700"
          data-testid="delete-current-bloc-btn"
        >
          <Trash size={14} weight="duotone" />
          {t('blocs.deleteTitle')}
        </Button>
      </SectionHead>

      {/* Vues enregistrées : rappel d'un jeu tri + filtres, à côté du bloc. */}
      {blocViews.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2" data-testid="saved-views">
          <span className="text-[11px] uppercase tracking-[0.09em] text-ink/[0.5]">
            {t('views.saved')}
          </span>
          {blocViews.map((v) => (
            <span key={v.slug} className="tag tag-outline gap-1.5">
              <button
                type="button"
                onClick={() => applyView(v)}
                className="border-0 bg-transparent p-0 text-inherit"
                data-testid={`apply-view-${v.slug}`}
              >
                {v.label}
              </button>
              <button
                type="button"
                onClick={() => deleteViewMutation.mutate(v.slug)}
                aria-label={`${t('views.delete')} ${v.label}`}
                className="border-0 bg-transparent p-0 text-inherit"
                data-testid={`delete-view-${v.slug}`}
              >
                <Trash size={11} weight="duotone" />
              </button>
            </span>
          ))}
        </div>
      )}

      <ActiveFilterBar
        spec={spec}
        labelOf={propLabelOf}
        valueLabelOf={propValueLabelOf}
        onRemoveFilter={(prop) => setFilter(prop, null)}
        onClearAll={reset}
        onSaveView={() => setShowSaveView(true)}
      />

      {/* Barre : taille de page (mémorisée) + total ; la navigation se fait par
          « Charger plus » sous la table (accumulation). */}
      <div
        className="mb-4 flex items-center gap-3 text-[13px] text-ink/[0.55]"
        data-testid="docs-toolbar"
      >
        <label className="flex items-center gap-1.5">
          <span>{t('documents.perPage')}</span>
          <select
            className="input !w-auto"
            value={pageSize}
            onChange={(e) => changePageSize(Number(e.target.value))}
            data-testid="page-size-select"
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <span data-testid="docs-count">
          {t('documents.count', { count: mode === 'query' ? queryTotal : browseTotal })}
        </span>
        {mode === 'query' && (
          <Button variant="secondary" size="sm" onClick={reset} data-testid="query-clear-btn">
            {t('documents.clearQuery')}
          </Button>
        )}
      </div>

      {isEmpty ? (
        /* État vide explicite : un filtre trop restrictif ne rend pas une table
           blanche, il dit pourquoi et propose de relâcher les filtres. */
        <EmptyState
          testId="documents-empty"
          message={mode === 'query' ? t('documents.emptyFiltered') : t('documents.emptyBloc')}
          action={
            mode === 'query' ? (
              <Button variant="secondary" onClick={reset} data-testid="empty-clear-filters">
                {t('documents.clearAll')}
              </Button>
            ) : (
              <Button onClick={() => setDialogParent(null)}>
                <Plus size={16} weight="duotone" /> {t('documents.add')}
              </Button>
            )
          }
        />
      ) : (
        <table className="table" data-testid="documents-table">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => {
                  const sortKey = headerSortKey(header.column.id)
                  const sortState = sortKey ? sortStateFor(sortKey) : null
                  // Le rang n'est affiché que sur un tri multi-clé (mode requête).
                  const showRank = mode === 'query' && spec.sort.length > 1 && sortState
                  const propCol = propColById.get(header.column.id)
                  return (
                    <th
                      key={header.id}
                      className={sortKey ? 'cursor-pointer select-none' : undefined}
                      aria-sort={
                        sortState ? (sortState.dir === 'asc' ? 'ascending' : 'descending') : undefined
                      }
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
                          /* La colonne triée porte une flèche cyan ; le rang
                             n'apparaît que sur un tri multi-clé. */
                          <span className="inline-flex items-center text-accent" data-testid={`sort-arrow-${sortKey}`}>
                            {sortState.dir === 'asc'
                              ? <ArrowUp size={12} weight="bold" />
                              : <ArrowDown size={12} weight="bold" />}
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
                className="cursor-pointer"
                onClick={() => navigate(`/ws/${ws}/blocs/${block}/documents/${row.original.id}`)}
                data-testid={`doc-row-${row.original.id}`}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData(
                    'application/x-docflow-doc',
                    JSON.stringify({
                      id: row.original.id,
                      title: row.original.title,
                      type: row.original.functional_type_slug,
                    }),
                  )
                  e.dataTransfer.effectAllowed = 'move'
                }}
                onDragOver={(e) => {
                  if (e.dataTransfer.types.includes('application/x-docflow-doc')) e.preventDefault()
                }}
                onDrop={(e) => {
                  const raw = e.dataTransfer.getData('application/x-docflow-doc')
                  if (!raw) return
                  e.preventDefault()
                  e.stopPropagation()
                  const dragged = JSON.parse(raw) as { id: string; title: string; type: string | null }
                  if (dragged.id === row.original.id) return
                  setReparentDrop({ doc: dragged, target: row.original.id })
                }}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* « Charger plus » : ajoute la page suivante à la suite (accumulation). */}
      {!isEmpty && (mode === 'query' ? queryInfinite.hasNextPage : browseInfinite.hasNextPage) && (
        <div className="mt-3 flex justify-center">
          <Button
            variant="secondary"
            onClick={() =>
              mode === 'query' ? queryInfinite.fetchNextPage() : browseInfinite.fetchNextPage()
            }
            disabled={
              mode === 'query'
                ? queryInfinite.isFetchingNextPage
                : browseInfinite.isFetchingNextPage
            }
            data-testid="load-more-btn"
          >
            {(mode === 'query'
              ? queryInfinite.isFetchingNextPage
              : browseInfinite.isFetchingNextPage)
              ? t('common.loading')
              : t('documents.loadMore')}
          </Button>
        </div>
      )}

      <div
        className="mt-3 rounded-md border border-dashed border-[var(--color-divider)] px-3 py-2 text-[12px] text-ink/[0.45]"
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes('application/x-docflow-doc')) e.preventDefault()
        }}
        onDrop={(e) => {
          const raw = e.dataTransfer.getData('application/x-docflow-doc')
          if (!raw) return
          e.preventDefault()
          const dragged = JSON.parse(raw) as { id: string; title: string; type: string | null }
          setReparentDrop({ doc: dragged, target: null })
        }}
        data-testid="reparent-root-dropzone"
      >
        Déposer ici pour placer à la racine du bloc — ou déposer une ligne sur une autre pour changer de parent.
      </div>

      {reparentDrop && ws && block && (
        <ReparentDialog
          ws={ws}
          block={block}
          doc={reparentDrop.doc}
          newParentId={reparentDrop.target}
          onDone={() => {
            setReparentDrop(null)
            void queryClient.invalidateQueries({ queryKey: ['block-tree', ws, block] })
            void queryClient.invalidateQueries()
          }}
          onCancel={() => setReparentDrop(null)}
        />
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

      {showSaveView && (
        <div className="dialog-backdrop z-50" data-testid="save-view-dialog">
          <form
            className="dialog"
            onSubmit={(e) => {
              e.preventDefault()
              const label = new FormData(e.currentTarget).get('label')
              if (typeof label === 'string' && label.trim()) saveViewMutation.mutate(label.trim())
            }}
          >
            <h4 className="dialog-title">{t('views.saveTitle')}</h4>
            <p className="dialog-body">{t('views.saveHint')}</p>
            <Field label={t('views.namePrompt')} htmlFor="view-label">
              <Input id="view-label" name="label" autoFocus required />
            </Field>
            <div className="dialog-actions">
              <Button variant="secondary" type="button" onClick={() => setShowSaveView(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={saveViewMutation.isPending}>
                {t('views.save')}
              </Button>
            </div>
          </form>
        </div>
      )}

      {showDeleteBloc && ws && block && (
        <DeleteBlocDialog
          wsSlug={ws}
          blockSlug={block}
          blockLabel={blocLabel}
          documentsCount={currentBloc?.documents_count ?? 0}
          onClose={() => setShowDeleteBloc(false)}
          onDeleted={handleBlocDeleted}
        />
      )}
    </div>
  )
}

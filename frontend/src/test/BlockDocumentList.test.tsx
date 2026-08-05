import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    docsApi: {
      ...actual.docsApi,
      getBlockDocuments: vi.fn(),
      getPresentTypeSlugs: vi.fn(),
      getTypesRich: vi.fn(),
      getBlockTree: vi.fn(),
      getAllowedTypes: vi.fn(),
      createDocument: vi.fn(),
      queryBlockDocuments: vi.fn(),
      getDocumentValues: vi.fn(),
      putDocumentValue: vi.fn(),
    },
    viewsApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
    prefsApi: { get: vi.fn(), set: vi.fn() },
  }
})

import {
  docsApi,
  prefsApi,
  viewsApi,
  type BlockTreeNode,
  type BlockTreePage,
  type DocumentOut,
  type FunctionalTypeRich,
  type PropertyValueBrief,
} from '../lib/api'
import { BlockDocumentList } from '../pages/BlockDocumentList'

function makeDoc(over: Partial<DocumentOut>): DocumentOut {
  return {
    doc_technical_key: 'd1',
    title: 'Doc',
    type: 'page',
    slug: null,
    content: null,
    version: 1,
    parent_id: null,
    functional_type_slug: 'epic',
    workspace_slug: 'ws',
    data_block_ref: 'b1',
    exposed: false,
    created_at: '',
    updated_at: '',
    updated_by: null,
    ...over,
  }
}

/** Assemble un `BlockTreePage` (mode browse) à partir des mêmes docs plats
 *  utilisés côté `getBlockDocuments`, façon `list_block_tree` côté serveur. */
function makeTreePage(
  docs: DocumentOut[],
  propsByDoc: Record<string, PropertyValueBrief[]> = {},
): BlockTreePage {
  const byParent = new Map<string | null, DocumentOut[]>()
  for (const d of docs) {
    const arr = byParent.get(d.parent_id) ?? []
    arr.push(d)
    byParent.set(d.parent_id, arr)
  }
  const toNode = (doc: DocumentOut): BlockTreeNode => ({
    id: doc.doc_technical_key,
    title: doc.title,
    functional_type_slug: doc.functional_type_slug,
    parent_id: doc.parent_id,
    updated_at: null,
    updated_by: null,
    properties: propsByDoc[doc.doc_technical_key] ?? [],
    children: (byParent.get(doc.doc_technical_key) ?? []).map(toNode),
  })
  const roots = (byParent.get(null) ?? []).map(toNode)
  return { block_slug: 'b1', page: 1, page_size: 100, total: roots.length, has_next: false, roots }
}

const emptyTypesRich: FunctionalTypeRich[] = []
const emptyTreePage: BlockTreePage = {
  block_slug: 'b1',
  page: 1,
  page_size: 25,
  total: 0,
  has_next: false,
  roots: [],
}

function renderList(url = '/ws/ws/blocs/b1/documents') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route
            path="/ws/:wsSlug/blocs/:blocSlug/documents"
            element={<BlockDocumentList />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BlockDocumentList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(docsApi.getTypesRich).mockResolvedValue(emptyTypesRich)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(emptyTreePage)
    // Les colonnes de propriétés dérivent des types PRÉSENTS : on les dérive des
    // documents encore mockés via getBlockDocuments (source d'intention des tests).
    vi.mocked(docsApi.getPresentTypeSlugs).mockImplementation(async () => {
      const docs = await vi.mocked(docsApi.getBlockDocuments)('ws', 'b1').catch(() => [])
      return [...new Set(docs.map((d) => d.functional_type_slug).filter(Boolean) as string[])]
    })
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([])
    vi.mocked(viewsApi.list).mockResolvedValue([])
    vi.mocked(prefsApi.get).mockResolvedValue({ key: 'k', value: null })
    vi.mocked(prefsApi.set).mockResolvedValue({ key: 'k', value: null })
  })

  // DoD 26.1 — état vide : une phrase et l'action de création, pas une table blanche.
  it('shows empty state', async () => {
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([])
    renderList()
    const empty = await screen.findByTestId('documents-empty')
    expect(empty).toHaveTextContent('aucun document')
    expect(empty.querySelector('button')).not.toBeNull()
  })

  // DoD 26.2 — arbre indenté + toggle
  it('renders a tree of documents', async () => {
    const docs = [
      makeDoc({ doc_technical_key: 'parent', title: 'Parent', parent_id: null }),
      makeDoc({ doc_technical_key: 'child', title: 'Child', parent_id: 'parent' }),
    ]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    renderList()
    await waitFor(() => expect(screen.getByTestId('documents-table')).toBeInTheDocument())
    expect(screen.getByText('Parent')).toBeInTheDocument()
    expect(screen.getByTestId('add-root-btn')).toBeInTheDocument()
  })

  it('la taille de page est configurable et mémorisée en préférence', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    renderList()
    // Chargement initial avec la taille par défaut (25).
    await waitFor(() => expect(docsApi.getBlockTree).toHaveBeenCalledWith('ws', 'b1', 1, 25, 'title', 'asc'))
    const select = await screen.findByTestId('page-size-select')

    fireEvent.change(select, { target: { value: '50' } })
    // Persistée en préférence + re-fetch avec la nouvelle taille.
    await waitFor(() => expect(prefsApi.set).toHaveBeenCalledWith('doc-page-size', 50))
    await waitFor(() => expect(docsApi.getBlockTree).toHaveBeenCalledWith('ws', 'b1', 1, 50, 'title', 'asc'))
  })

  // DoD 26.3 — colonnes dynamiques : budget_jours présent sur epic, absent sur feature
  it('shows dynamic property column with value for epic, empty for feature', async () => {
    const docs = [
      makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' }),
      makeDoc({
        doc_technical_key: 'f1',
        title: 'Feature 1',
        functional_type_slug: 'feature',
        parent_id: 'e1',
      }),
    ]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([
      {
        id: 'tid-epic',
        slug: 'epic',
        label: 'Epic',
        parent_slug: null,
        workspace_slug: 'ws',
        content_template: null,
        source_template: null,
        created_at: '',
        updated_at: '',
        documents_count: 0,
        properties: [
          {
            slug: 'budget_jours',
            label: 'Budget (jours)',
            type: 'int',
            default_value: null,
          behavior: null,
            required: false,
            allowed_values: [],
          },
        ],
      },
      {
        id: 'tid-feature',
        slug: 'feature',
        label: 'Feature',
        parent_slug: 'epic',
        workspace_slug: 'ws',
        content_template: null,
        source_template: null,
        created_at: '',
        updated_at: '',
        documents_count: 0,
        properties: [],
      },
    ])
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(
      makeTreePage(docs, {
        e1: [
          {
            prop_slug: 'budget_jours',
            type: 'int',
            value: '10',
            allowed_value_slug: null,
            allowed_value_label: null,
          },
        ],
      }),
    )
    renderList()
    await waitFor(() => expect(screen.getByText('Budget (jours)')).toBeInTheDocument())
    // Epic a la valeur
    expect(screen.getByText('10')).toBeInTheDocument()
  })

  // DoD 26.3 — dropdown colonnes
  it('opens column visibility dropdown', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([
      {
        id: 'tid',
        slug: 'epic',
        label: 'Epic',
        parent_slug: null,
        workspace_slug: 'ws',
        content_template: null,
        source_template: null,
        created_at: '',
        updated_at: '',
        documents_count: 0,
        properties: [
          {
            slug: 'budget_jours',
            label: 'Budget (jours)',
            type: 'int',
            default_value: null,
          behavior: null,
            required: false,
            allowed_values: [],
          },
        ],
      },
    ])
    renderList()
    await waitFor(() => expect(screen.getByTestId('columns-btn')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('columns-btn'))
    await waitFor(() => expect(screen.getByTestId('columns-menu')).toBeInTheDocument())
    expect(screen.getByTestId('col-toggle-prop_budget_jours')).toBeInTheDocument()
  })

  // DoD 26.4 — bouton + sous parent → AddDocumentDialog s'ouvre
  it('opens add-document dialog when clicking + on a row', async () => {
    const docs = [
      makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', parent_id: null, functional_type_slug: 'epic' }),
    ]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    // types-rich doit exposer feature comme enfant d'epic pour que le bouton apparaisse
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([
      { id: 't1', slug: 'epic', label: 'Epic', parent_slug: null, workspace_slug: 'ws', content_template: null,
        source_template: null, created_at: '', updated_at: '', documents_count: 0, properties: [] },
      { id: 't2', slug: 'feature', label: 'Feature', parent_slug: 'epic', workspace_slug: 'ws', content_template: null,
        source_template: null, created_at: '', updated_at: '', documents_count: 0, properties: [] },
    ])
    vi.mocked(docsApi.getAllowedTypes).mockResolvedValue([
      { slug: 'feature', label: 'Feature' },
    ])
    renderList()
    await waitFor(() => expect(screen.getByTestId('add-child-e1')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('add-child-e1'))
    // getAllowedTypes est appelé quand le dialog s'ouvre (pour charger les types enfants dans le dialog)
    await waitFor(() => expect(vi.mocked(docsApi.getAllowedTypes)).toHaveBeenCalledWith(
      'ws', 'b1', 'e1'
    ))
  })

  // US État QuerySpec front + bascule browse↔requête : un filtre d'entête
  // bascule en mode requête (serveur, liste plate) — plus de préservation de
  // chemin côté client, remplacée par l'appel serveur ≤100 lignes.
  it('setting a header filter switches to query mode and calls the server', async () => {
    const docs = [
      makeDoc({ doc_technical_key: 'epic1', title: 'Epic 1', functional_type_slug: 'epic', parent_id: null }),
      makeDoc({ doc_technical_key: 'feat1', title: 'Feature 1', functional_type_slug: 'feature', parent_id: 'epic1' }),
      makeDoc({ doc_technical_key: 'atdd1', title: 'ATDD done', functional_type_slug: 'atdd', parent_id: 'feat1' }),
      makeDoc({ doc_technical_key: 'story1', title: 'Story in-progress', functional_type_slug: 'story', parent_id: 'feat1' }),
    ]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([
      {
        id: 'tid-atdd',
        slug: 'atdd',
        label: 'ATDD',
        parent_slug: 'feature',
        workspace_slug: 'ws',
        content_template: null,
        source_template: null,
        created_at: '',
        updated_at: '',
        documents_count: 0,
        properties: [
          {
            slug: 'statut',
            label: 'Statut',
            type: 'restricted_list',
            default_value: null,
            behavior: null,
            required: false,
            allowed_values: [
              { slug: 'done', label: 'Terminé', position: 1, color: '#22c55e' },
              { slug: 'in-progress', label: 'En cours', position: 0, color: '#f59e0b' },
            ],
          },
        ],
      },
    ])
    vi.mocked(docsApi.queryBlockDocuments).mockResolvedValue({
      block_slug: 'b1',
      page: 1,
      page_size: 25,
      total: 1,
      has_next: false,
      objects: [
        {
          id: 'atdd1',
          title: 'ATDD done',
          functional_type_slug: 'atdd',
          updated_at: null,
          updated_by: null,
          properties: [
            { prop_slug: 'statut', type: 'restricted_list', value: null, allowed_value_slug: 'done', allowed_value_label: 'Terminé' },
          ],
        },
      ],
    })

    renderList()
    await waitFor(() => expect(screen.getByTestId('filter-btn-statut')).toBeInTheDocument())

    await applyRestrictedFilter('statut', ['done'])

    await waitFor(() => {
      expect(docsApi.queryBlockDocuments).toHaveBeenCalledWith('ws', 'b1', {
        filters: [{ prop: 'statut', op: 'in', values: ['done'] }],
        sort: [],
        projection: null,
        page: 1,
        page_size: 25,
      })
    })
    await waitFor(() => expect(screen.getByText('ATDD done')).toBeInTheDocument())
    // Mode requête = liste plate serveur : plus de préservation de chemin.
    expect(screen.queryByText('Feature 1')).not.toBeInTheDocument()
    expect(screen.queryByText('Epic 1')).not.toBeInTheDocument()
    expect(screen.queryByText('Story in-progress')).not.toBeInTheDocument()
    // Le mode requête masque le bouton arbre/liste (flat forcé) et affiche la
    // barre (avec le bouton d'effacement de requête).
    expect(screen.queryByTestId('toggle-view-btn')).not.toBeInTheDocument()
    expect(screen.getByTestId('docs-toolbar')).toBeInTheDocument()
    expect(screen.getByTestId('query-clear-btn')).toBeInTheDocument()

    // Effacer la requête revient en mode browse (arbre paginé, sans appel serveur
    // supplémentaire). Les statuts n'étant pas renseignés ici, l'arbre démarre
    // replié : seule la racine est visible (les descendants sont collapsés).
    fireEvent.click(screen.getByTestId('query-clear-btn'))
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())
    expect(screen.queryByText('Story in-progress')).not.toBeInTheDocument()
    expect(screen.getByTestId('docs-toolbar')).toBeInTheDocument()
    expect(screen.queryByTestId('query-clear-btn')).not.toBeInTheDocument()
  })

  it('in query mode, clicking the title header cycles server sort (asc → desc)', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([statutType()])
    vi.mocked(docsApi.queryBlockDocuments).mockResolvedValue({
      block_slug: 'b1',
      page: 1,
      page_size: 25,
      total: 1,
      has_next: false,
      objects: [{ id: 'e1', title: 'Epic 1', functional_type_slug: 'epic', updated_at: null, updated_by: null, properties: [] }],
    })

    renderList()
    // Entrer en mode requête via un filtre (le clic d'entête ne bascule plus le mode).
    await waitFor(() => expect(screen.getByTestId('filter-btn-statut')).toBeInTheDocument())
    await applyRestrictedFilter('statut', ['done'])
    // Attendre la résolution de la requête (la ligne apparaît) avant de trier.
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Titre'))
    await waitFor(() =>
      expect(docsApi.queryBlockDocuments).toHaveBeenLastCalledWith('ws', 'b1', {
        filters: [{ prop: 'statut', op: 'in', values: ['done'] }],
        sort: [{ key: 'title', dir: 'asc' }],
        projection: null,
        page: 1,
        page_size: 25,
      }),
    )
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())

    fireEvent.click(screen.getByText(/Titre/))
    await waitFor(() =>
      expect(docsApi.queryBlockDocuments).toHaveBeenLastCalledWith('ws', 'b1', {
        filters: [{ prop: 'statut', op: 'in', values: ['done'] }],
        sort: [{ key: 'title', dir: 'desc' }],
        projection: null,
        page: 1,
        page_size: 25,
      }),
    )
  })

  it('charge la page suivante en mode requête via « Charger plus »', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([statutType()])
    vi.mocked(docsApi.queryBlockDocuments).mockResolvedValue({
      block_slug: 'b1',
      page: 1,
      page_size: 25,
      total: 250,
      has_next: true,
      objects: [{ id: 'e1', title: 'Epic 1', functional_type_slug: 'epic', updated_at: null, updated_by: null, properties: [] }],
    })

    renderList()
    // Entrer en mode requête via un filtre.
    await waitFor(() => expect(screen.getByTestId('filter-btn-statut')).toBeInTheDocument())
    await applyRestrictedFilter('statut', ['done'])
    // has_next=true → bouton « Charger plus » présent.
    await waitFor(() => expect(screen.getByTestId('load-more-btn')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('load-more-btn'))
    await waitFor(() =>
      expect(docsApi.queryBlockDocuments).toHaveBeenLastCalledWith('ws', 'b1', {
        filters: [{ prop: 'statut', op: 'in', values: ['done'] }],
        sort: [],
        projection: null,
        page: 2,
        page_size: 25,
      }),
    )
  })

  // US Tri hiérarchique sur la page courante (parents puis enfants).
  it('sorts the tree server-side on header click, staying in browse mode', async () => {
    const docs = [
      makeDoc({ doc_technical_key: 'ea', title: 'Epic A', functional_type_slug: 'epic', parent_id: null }),
      makeDoc({ doc_technical_key: 'eb', title: 'Epic B', functional_type_slug: 'epic', parent_id: null }),
      makeDoc({ doc_technical_key: 'fz', title: 'Feat Z', functional_type_slug: 'feature', parent_id: 'ea' }),
      makeDoc({ doc_technical_key: 'fx', title: 'Feat X', functional_type_slug: 'feature', parent_id: 'ea' }),
    ]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    // Le tri est CÔTÉ SERVEUR : le mock ordonne racines + enfants selon (sort, dir).
    vi.mocked(docsApi.getBlockTree).mockImplementation(
      async (_ws, _b, _page, _size, _sort = 'title', dir = 'asc') => {
        const ordered = [...docs].sort((a, b) => {
          const r = a.title.localeCompare(b.title)
          return dir === 'desc' ? -r : r
        })
        return makeTreePage(ordered, { fz: [statut('done')], fx: [statut('en_cours')] })
      },
    )
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([])

    const rowOrder = () =>
      screen.getAllByTestId(/^doc-row-/).map((el) => el.getAttribute('data-testid'))

    renderList()
    await waitFor(() => expect(screen.getByText('Feat X')).toBeInTheDocument())
    // Défaut serveur = title asc : racines A avant B ; sous A, X avant Z.
    expect(rowOrder()).toEqual(['doc-row-ea', 'doc-row-fx', 'doc-row-fz', 'doc-row-eb'])

    // 1er clic : asc (déjà le défaut) — reste en mode browse, pas de bascule requête.
    fireEvent.click(screen.getByText('Titre'))
    expect(docsApi.queryBlockDocuments).not.toHaveBeenCalled()
    expect(screen.getByTestId('docs-toolbar')).toBeInTheDocument()
    expect(screen.queryByTestId('query-clear-btn')).not.toBeInTheDocument()

    // 2e clic : desc → refetch serveur avec dir=desc ; B avant A, Z avant X.
    fireEvent.click(screen.getByText(/Titre/))
    await waitFor(() =>
      expect(docsApi.getBlockTree).toHaveBeenLastCalledWith('ws', 'b1', 1, 25, 'title', 'desc'),
    )
    await waitFor(() =>
      expect(rowOrder()).toEqual(['doc-row-eb', 'doc-row-ea', 'doc-row-fz', 'doc-row-fx']),
    )

    // 3e clic : tri annulé → retour au défaut serveur (title asc).
    fireEvent.click(screen.getByText(/Titre/))
    await waitFor(() =>
      expect(rowOrder()).toEqual(['doc-row-ea', 'doc-row-fx', 'doc-row-fz', 'doc-row-eb']),
    )
  })

  it('sorts browse by the "Modifié" column server-side (updated_at)', async () => {
    const docs = [
      makeDoc({ doc_technical_key: 'ea', title: 'Epic A', functional_type_slug: 'epic', parent_id: null }),
      makeDoc({ doc_technical_key: 'eb', title: 'Epic B', functional_type_slug: 'epic', parent_id: null }),
    ]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([])

    renderList()
    await waitFor(() => expect(screen.getByText('Epic A')).toBeInTheDocument())

    // Clic sur l'entête « Modifié » → tri serveur par updated_at (reste en browse).
    fireEvent.click(screen.getByTestId('sort-header-updated_at'))
    await waitFor(() =>
      expect(docsApi.getBlockTree).toHaveBeenLastCalledWith('ws', 'b1', 1, 25, 'updated_at', 'asc'),
    )
    expect(docsApi.queryBlockDocuments).not.toHaveBeenCalled()
  })

  // US Tri par clic d'entête branché au moteur serveur (+ multi-clé Maj-clic).
  it('in query mode, sorts by a property column and composes a multi-key sort with Maj-click', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([statutType()])
    vi.mocked(docsApi.queryBlockDocuments).mockResolvedValue({
      block_slug: 'b1',
      page: 1,
      page_size: 25,
      total: 1,
      has_next: false,
      objects: [
        {
          id: 'e1',
          title: 'Epic 1',
          updated_at: null,
          updated_by: null,
          functional_type_slug: 'epic',
          properties: [statut('done')],
        },
      ],
    })

    renderList()
    // Entrer en mode requête via un filtre (les colonnes de propriété deviennent triables).
    await waitFor(() => expect(screen.getByTestId('filter-btn-statut')).toBeInTheDocument())
    await applyRestrictedFilter('statut', ['done'])
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())

    // Tri serveur par la colonne de propriété statut (clé = slug de propriété).
    fireEvent.click(screen.getByTestId('sort-header-statut'))
    await waitFor(() =>
      expect(docsApi.queryBlockDocuments).toHaveBeenLastCalledWith('ws', 'b1', {
        filters: [{ prop: 'statut', op: 'in', values: ['done'] }],
        sort: [{ key: 'statut', dir: 'asc' }],
        projection: null,
        page: 1,
        page_size: 25,
      }),
    )
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())

    // Maj-clic sur le titre → tri multi-clé (statut puis title, ordre = précédence).
    fireEvent.click(screen.getByTestId('sort-header-title'), { shiftKey: true })
    await waitFor(() =>
      expect(docsApi.queryBlockDocuments).toHaveBeenLastCalledWith('ws', 'b1', {
        filters: [{ prop: 'statut', op: 'in', values: ['done'] }],
        sort: [
          { key: 'statut', dir: 'asc' },
          { key: 'title', dir: 'asc' },
        ],
        projection: null,
        page: 1,
        page_size: 25,
      }),
    )
  })

  // US Sélecteur de colonnes (projection du QuerySpec).
  it('in query mode, hiding a column reduces the projection sent to the server', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([
      {
        id: 'tid-epic',
        slug: 'epic',
        label: 'Epic',
        parent_slug: null,
        workspace_slug: 'ws',
        content_template: null,
        source_template: null,
        created_at: '',
        updated_at: '',
        documents_count: 0,
        properties: [
          {
            slug: 'statut',
            label: 'Statut',
            type: 'restricted_list',
            default_value: null,
            behavior: null,
            required: false,
            allowed_values: [{ slug: 'done', label: 'Terminé', position: 1, color: '#22c55e' }],
          },
          {
            slug: 'points',
            label: 'Points',
            type: 'int',
            default_value: null,
            behavior: null,
            required: false,
            allowed_values: [],
          },
        ],
      },
    ])
    vi.mocked(docsApi.queryBlockDocuments).mockResolvedValue({
      block_slug: 'b1',
      page: 1,
      page_size: 25,
      total: 1,
      has_next: false,
      objects: [{ id: 'e1', title: 'Epic 1', functional_type_slug: 'epic', updated_at: null, updated_by: null, properties: [statut('done')] }],
    })

    renderList()
    await waitFor(() => expect(screen.getByTestId('filter-btn-statut')).toBeInTheDocument())
    await applyRestrictedFilter('statut', ['done'])
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())
    // Projection initiale = toutes les colonnes visibles → null (le serveur remonte tout).
    expect(docsApi.queryBlockDocuments).toHaveBeenLastCalledWith(
      'ws',
      'b1',
      expect.objectContaining({ projection: null }),
    )

    // Masquer la colonne « Points » via le sélecteur de colonnes.
    fireEvent.click(screen.getByTestId('columns-btn'))
    await waitFor(() => expect(screen.getByTestId('col-toggle-prop_points')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('col-toggle-prop_points'))

    // La requête est rejouée avec une projection réduite aux colonnes visibles.
    await waitFor(() =>
      expect(docsApi.queryBlockDocuments).toHaveBeenLastCalledWith(
        'ws',
        'b1',
        expect.objectContaining({ projection: ['statut'] }),
      ),
    )
  })

  // US Édition inline des propriétés dans les cellules.
  it('inline-edits a restricted_list cell and refreshes the table', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs, { e1: [statut('a_faire')] }))
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([
      {
        id: 'tid-epic',
        slug: 'epic',
        label: 'Epic',
        parent_slug: null,
        workspace_slug: 'ws',
        content_template: null,
        source_template: null,
        created_at: '',
        updated_at: '',
        documents_count: 0,
        properties: [
          {
            slug: 'statut',
            label: 'Statut',
            type: 'restricted_list',
            default_value: null,
            behavior: null,
            required: true,
            allowed_values: [
              { slug: 'a_faire', label: 'À faire', position: 0, color: '#999' },
              { slug: 'done', label: 'Done', position: 1, color: '#22c55e' },
            ],
          },
        ],
      },
    ])
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([
      {
        prop_slug: 'statut',
        prop_label: 'Statut',
        type: 'restricted_list',
        version: 2,
        value: null,
        allowed_value_slug: 'a_faire',
        allowed_value_label: 'À faire',
        required: true,
        behavior: null,
      },
    ])
    vi.mocked(docsApi.putDocumentValue).mockResolvedValue({
      prop_slug: 'statut',
      prop_label: 'Statut',
      type: 'restricted_list',
      version: 3,
      value: null,
      allowed_value_slug: 'done',
      allowed_value_label: 'Done',
      required: true,
      behavior: null,
    })

    renderList()
    await waitFor(() => expect(screen.getByTestId('inline-cell-statut-e1')).toBeInTheDocument())
    const treeCallsBefore = vi.mocked(docsApi.getBlockTree).mock.calls.length

    // Clic sur la cellule → contrôle inline (après récupération de la version).
    fireEvent.click(screen.getByTestId('inline-cell-statut-e1'))
    await waitFor(() => expect(screen.getByTestId('property-input-statut')).toBeInTheDocument())

    // Choisir « Done » → sauvegarde avec la version courante.
    fireEvent.change(screen.getByTestId('property-input-statut'), { target: { value: 'done' } })
    await waitFor(() =>
      expect(docsApi.putDocumentValue).toHaveBeenCalledWith('ws', 'e1', 'statut', {
        allowed_value_slug: 'done',
        expected_version: 2,
      }),
    )
    // La table est rafraîchie (list_block_tree rejoué après invalidation).
    await waitFor(() =>
      expect(vi.mocked(docsApi.getBlockTree).mock.calls.length).toBeGreaterThan(treeCallsBefore),
    )
  })

  // « Charger plus » en mode browse : la page suivante de racines s'ajoute.
  it('charge la page suivante en mode browse via « Charger plus » (list_block_tree)', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue({
      block_slug: 'b1',
      page: 1,
      page_size: 25,
      total: 250,
      has_next: true,
      roots: docs.map((d) => ({
        id: d.doc_technical_key,
        title: d.title,
        updated_at: null,
        updated_by: null,
        functional_type_slug: d.functional_type_slug,
        parent_id: d.parent_id,
        properties: [],
        children: [],
      })),
    })
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([])

    renderList()
    // Première page chargée avec la taille par défaut (25), has_next → « Charger plus ».
    await waitFor(() => expect(docsApi.getBlockTree).toHaveBeenCalledWith('ws', 'b1', 1, 25, 'title', 'asc'))
    await waitFor(() => expect(screen.getByTestId('load-more-btn')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('load-more-btn'))
    await waitFor(() => expect(docsApi.getBlockTree).toHaveBeenLastCalledWith('ws', 'b1', 2, 25, 'title', 'asc'))
  })

  // Applique un filtre restricted_list via le popover d'entête (op `in`).
  // Ouvre le popover, coche la/les valeur(s), puis clique « Appliquer ».
  async function applyRestrictedFilter(propSlug: string, valueSlugs: string[]) {
    fireEvent.click(screen.getByTestId(`filter-btn-${propSlug}`))
    await waitFor(() => expect(screen.getByTestId(`filter-popover-${propSlug}`)).toBeInTheDocument())
    for (const v of valueSlugs) {
      fireEvent.click(screen.getByTestId(`filter-opt-${propSlug}-${v}`))
    }
    fireEvent.click(screen.getByTestId(`filter-apply-${propSlug}`))
  }

  // US Collapse par défaut si les enfants directs ont le même statut.
  function statut(slug: string): PropertyValueBrief {
    return {
      prop_slug: 'statut',
      type: 'restricted_list',
      value: null,
      allowed_value_slug: slug,
      allowed_value_label: slug,
    }
  }

  // Type epic portant une propriété statut (restricted_list) → filtre d'entête.
  function statutType(): FunctionalTypeRich {
    return {
      id: 'tid-epic',
      slug: 'epic',
      label: 'Epic',
      parent_slug: null,
      workspace_slug: 'ws',
      content_template: null,
        source_template: null,
      created_at: '',
      updated_at: '',
      documents_count: 0,
      properties: [
        {
          slug: 'statut',
          label: 'Statut',
          type: 'restricted_list',
          default_value: null,
          behavior: null,
          required: false,
          allowed_values: [
            { slug: 'done', label: 'Terminé', position: 1, color: '#22c55e' },
            { slug: 'en_cours', label: 'En cours', position: 0, color: '#f59e0b' },
          ],
        },
      ],
    }
  }

  it('starts a parent collapsed when its direct children share the same status', async () => {
    const docs = [
      makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic', parent_id: null }),
      makeDoc({ doc_technical_key: 'f1', title: 'Feature A', functional_type_slug: 'feature', parent_id: 'e1' }),
      makeDoc({ doc_technical_key: 'f2', title: 'Feature B', functional_type_slug: 'feature', parent_id: 'e1' }),
    ]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(
      makeTreePage(docs, { f1: [statut('done')], f2: [statut('done')] }),
    )
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([])

    renderList()
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())
    // Enfants homogènes (done/done) → parent replié : enfants masqués.
    expect(screen.queryByText('Feature A')).not.toBeInTheDocument()
    expect(screen.queryByText('Feature B')).not.toBeInTheDocument()

    // L'utilisateur peut toujours déplier manuellement.
    fireEvent.click(screen.getByTestId('expand-e1'))
    await waitFor(() => expect(screen.getByText('Feature A')).toBeInTheDocument())
    expect(screen.getByText('Feature B')).toBeInTheDocument()
  })

  it('starts a parent expanded when its direct children have divergent statuses', async () => {
    const docs = [
      makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic', parent_id: null }),
      makeDoc({ doc_technical_key: 'f1', title: 'Feature A', functional_type_slug: 'feature', parent_id: 'e1' }),
      makeDoc({ doc_technical_key: 'f2', title: 'Feature B', functional_type_slug: 'feature', parent_id: 'e1' }),
    ]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(
      makeTreePage(docs, { f1: [statut('done')], f2: [statut('en_cours')] }),
    )
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([])

    renderList()
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())
    // Statuts divergents (done vs en_cours) → parent déplié d'emblée.
    expect(screen.getByText('Feature A')).toBeInTheDocument()
    expect(screen.getByText('Feature B')).toBeInTheDocument()
  })

  it('keys collapse on statut only, ignoring other restricted_list props (e.g. severite)', async () => {
    // Cas `bug` : enfants avec severite divergente mais statut homogène → replié.
    const severite = (slug: string): PropertyValueBrief => ({
      prop_slug: 'severite',
      type: 'restricted_list',
      value: null,
      allowed_value_slug: slug,
      allowed_value_label: slug,
    })
    const docs = [
      makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic', parent_id: null }),
      makeDoc({ doc_technical_key: 'b1', title: 'Bug A', functional_type_slug: 'bug', parent_id: 'e1' }),
      makeDoc({ doc_technical_key: 'b2', title: 'Bug B', functional_type_slug: 'bug', parent_id: 'e1' }),
    ]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(
      makeTreePage(docs, {
        b1: [statut('done'), severite('majeure')],
        b2: [statut('done'), severite('mineure')],
      }),
    )
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([])

    renderList()
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())
    // severite diverge mais statut est homogène → parent replié.
    expect(screen.queryByText('Bug A')).not.toBeInTheDocument()
    expect(screen.queryByText('Bug B')).not.toBeInTheDocument()
  })
})

// ── Écran Documents Broadsheet : tri/filtres dans l'URL, chips, popover ──────

const TYPES_WITH_STATUS: FunctionalTypeRich[] = [
  {
    id: 't-epic', slug: 'epic', label: 'Epic', parent_slug: null, workspace_slug: 'ws',
    source_template: null, content_template: null, created_at: '', updated_at: '',
    documents_count: 0,
    properties: [
      {
        slug: 'statut', label: 'Statut', type: 'restricted_list', required: false,
        behavior: null, default_value: null,
        allowed_values: [
          { slug: 'en_cours', label: 'En cours', color: null, position: 0 },
          { slug: 'fait', label: 'Fait', color: null, position: 1 },
        ],
      },
    ],
  },
]

describe('BlockDocumentList — tri, filtres et URL', () => {
  const docs = [makeDoc({ doc_technical_key: 'd1', title: 'Alpha' })]

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(docsApi.getTypesRich).mockResolvedValue(TYPES_WITH_STATUS)
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(viewsApi.list).mockResolvedValue([])
    vi.mocked(prefsApi.get).mockResolvedValue({ key: 'k', value: null })
    vi.mocked(prefsApi.set).mockResolvedValue({ key: 'k', value: null })
    vi.mocked(docsApi.queryBlockDocuments).mockResolvedValue({
      objects: [], block_slug: 'b1', page: 1, page_size: 100, total: 0, has_next: false,
    })
  })

  it('hydrate le tri et les filtres depuis l’URL (partageable, survit au reload)', async () => {
    renderList('/ws/ws/blocs/b1/documents?f=statut:in:fait&sort=statut:desc')
    // Filtre présent → mode requête, la requête serveur reçoit la clause de l'URL.
    await waitFor(() =>
      expect(docsApi.queryBlockDocuments).toHaveBeenCalledWith('ws', 'b1', expect.objectContaining({
        filters: [{ prop: 'statut', op: 'in', values: ['fait'] }],
        sort: [{ key: 'statut', dir: 'desc' }],
      })),
    )
    // Et la chip du filtre actif est affichée avec le libellé de la valeur.
    expect(await screen.findByTestId('filter-chip-statut')).toHaveTextContent('Fait')
  })

  it('un filtre sans résultat affiche l’état vide et propose de l’effacer', async () => {
    renderList('/ws/ws/blocs/b1/documents?f=statut:in:fait')
    const empty = await screen.findByTestId('documents-empty')
    expect(empty).toHaveTextContent('Aucun document ne correspond')
    expect(screen.getByTestId('empty-clear-filters')).toBeInTheDocument()
  })

  it('retirer la chip d’un filtre revient en navigation', async () => {
    renderList('/ws/ws/blocs/b1/documents?f=statut:in:fait')
    fireEvent.click(await screen.findByTestId('filter-chip-remove-statut'))
    await waitFor(() => expect(screen.queryByTestId('filter-chip-statut')).not.toBeInTheDocument())
    expect(await screen.findByText('Alpha')).toBeInTheDocument()
  })

  it('le popover de filtre se ferme par Échap et rend le focus au déclencheur', async () => {
    renderList()
    const trigger = await screen.findByTestId('filter-btn-statut')
    fireEvent.click(trigger)
    expect(await screen.findByTestId('filter-popover-statut')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() =>
      expect(screen.queryByTestId('filter-popover-statut')).not.toBeInTheDocument(),
    )
    expect(trigger).toHaveFocus()
  })

  it('le popover se ferme au clic extérieur', async () => {
    renderList()
    fireEvent.click(await screen.findByTestId('filter-btn-statut'))
    expect(await screen.findByTestId('filter-popover-statut')).toBeInTheDocument()
    fireEvent.mouseDown(document.body)
    await waitFor(() =>
      expect(screen.queryByTestId('filter-popover-statut')).not.toBeInTheDocument(),
    )
  })

  it('la colonne triée porte une flèche cyan et aria-sort', async () => {
    // Il faut au moins une ligne : sans résultat, c'est l'état vide qui s'affiche.
    vi.mocked(docsApi.queryBlockDocuments).mockResolvedValue({
      objects: [{
        id: 'd1', title: 'Alpha', functional_type_slug: 'epic',
        updated_at: null, updated_by: null,
        properties: [{
          prop_slug: 'statut', type: 'restricted_list', value: null,
          allowed_value_slug: 'fait', allowed_value_label: 'Fait',
        }],
      }],
      block_slug: 'b1', page: 1, page_size: 100, total: 1, has_next: false,
    })
    renderList('/ws/ws/blocs/b1/documents?f=statut:in:fait&sort=statut:asc')
    const arrow = await screen.findByTestId('sort-arrow-statut')
    expect(arrow).toHaveClass('text-accent')
    expect(arrow.closest('th')).toHaveAttribute('aria-sort', 'ascending')
  })

  it('enregistre la sélection courante comme vue', async () => {
    vi.mocked(viewsApi.create).mockResolvedValue({
      id: 'v1', slug: 'ma-vue', label: 'Ma vue', layout: 'table', filter: [], sort: [],
      group_by: null, columns: [], bloc_ref: null, owner_ref: null, created_at: '', updated_at: '',
    })
    renderList('/ws/ws/blocs/b1/documents?f=statut:in:fait')
    fireEvent.click(await screen.findByTestId('save-view-btn'))
    const input = await screen.findByLabelText('Nom de la vue')
    fireEvent.change(input, { target: { value: 'Ma vue' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() =>
      expect(viewsApi.create).toHaveBeenCalledWith('ws', expect.objectContaining({
        slug: 'ma-vue',
        label: 'Ma vue',
        filter: [{ prop: 'statut', op: 'in', values: ['fait'] }],
      })),
    )
  })
})

describe('BlockDocumentList — colonnes mémorisées par utilisateur et par bloc', () => {
  const docs = [makeDoc({ doc_technical_key: 'd1', title: 'Alpha' })]

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(docsApi.getTypesRich).mockResolvedValue(TYPES_WITH_STATUS)
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(viewsApi.list).mockResolvedValue([])
    vi.mocked(prefsApi.get).mockResolvedValue({ key: 'k', value: null })
    vi.mocked(prefsApi.set).mockResolvedValue({ key: 'k', value: null })
  })

  it('masquer une colonne enregistre la préférence, clé user × bloc', async () => {
    renderList()
    fireEvent.click(await screen.findByTestId('columns-btn'))
    fireEvent.click(await screen.findByTestId('col-toggle-prop_statut'))
    await waitFor(() =>
      expect(prefsApi.set).toHaveBeenCalledWith('doc-columns:ws:b1',
        expect.objectContaining({ prop_statut: false })),
    )
  })

  it('la préférence enregistrée est appliquée à l’ouverture du bloc', async () => {
    vi.mocked(prefsApi.get).mockResolvedValue({
      key: 'doc-columns:ws:b1', value: { prop_statut: false },
    })
    renderList()
    await screen.findByText('Alpha')
    await waitFor(() =>
      expect(prefsApi.get).toHaveBeenCalledWith('doc-columns:ws:b1'),
    )
    // La colonne Statut est masquée dans la table…
    expect(screen.queryByRole('columnheader', { name: /Statut/ })).not.toBeInTheDocument()
    // …et son entrée du menu est décochée.
    fireEvent.click(screen.getByTestId('columns-btn'))
    expect(await screen.findByTestId('col-toggle-prop_statut')).not.toBeChecked()
  })

  it('tout réafficher efface la préférence (retour au défaut, pas un objet fantôme)', async () => {
    vi.mocked(prefsApi.get).mockResolvedValue({
      key: 'doc-columns:ws:b1', value: { prop_statut: false },
    })
    renderList()
    fireEvent.click(await screen.findByTestId('columns-btn'))
    fireEvent.click(await screen.findByTestId('col-toggle-prop_statut'))
    await waitFor(() =>
      expect(prefsApi.set).toHaveBeenCalledWith('doc-columns:ws:b1', null),
    )
  })

  it('l’état initial vide n’écrase JAMAIS la préférence avant hydratation', async () => {
    let resolveGet: (v: { key: string; value: null }) => void
    vi.mocked(prefsApi.get).mockReturnValue(new Promise((r) => { resolveGet = r }))
    renderList()
    await screen.findByText('Alpha')
    expect(prefsApi.set).not.toHaveBeenCalled()
    resolveGet!({ key: 'k', value: null })
  })
})

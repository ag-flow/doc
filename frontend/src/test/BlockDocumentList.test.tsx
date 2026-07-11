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
      getTypesRich: vi.fn(),
      getBlockTree: vi.fn(),
      getAllowedTypes: vi.fn(),
      createDocument: vi.fn(),
      queryBlockDocuments: vi.fn(),
    },
  }
})

import {
  docsApi,
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
  page_size: 100,
  total: 0,
  has_next: false,
  roots: [],
}

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/ws/ws/blocs/b1/documents']}>
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
  })

  // DoD 26.1 — état vide
  it('shows empty state', async () => {
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([])
    renderList()
    await waitFor(() => expect(screen.getByText('Aucun document')).toBeInTheDocument())
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
        created_at: '',
        updated_at: '',
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
        created_at: '',
        updated_at: '',
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
        created_at: '',
        updated_at: '',
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
      { id: 't1', slug: 'epic', label: 'Epic', parent_slug: null, workspace_slug: 'ws', content_template: null, created_at: '', updated_at: '', properties: [] },
      { id: 't2', slug: 'feature', label: 'Feature', parent_slug: 'epic', workspace_slug: 'ws', content_template: null, created_at: '', updated_at: '', properties: [] },
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
        created_at: '',
        updated_at: '',
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
      page_size: 100,
      total: 1,
      has_next: false,
      objects: [
        {
          id: 'atdd1',
          title: 'ATDD done',
          functional_type_slug: 'atdd',
          properties: [
            { prop_slug: 'statut', type: 'restricted_list', value: null, allowed_value_slug: 'done', allowed_value_label: 'Terminé' },
          ],
        },
      ],
    })

    renderList()
    await waitFor(() => expect(screen.getByTestId('filter-statut')).toBeInTheDocument())

    fireEvent.change(screen.getByTestId('filter-statut'), { target: { value: 'done' } })

    await waitFor(() => {
      expect(docsApi.queryBlockDocuments).toHaveBeenCalledWith('ws', 'b1', {
        filters: [{ prop: 'statut', op: 'eq', value: 'done' }],
        sort: [],
        projection: null,
        page: 1,
        page_size: 100,
      })
    })
    await waitFor(() => expect(screen.getByText('ATDD done')).toBeInTheDocument())
    // Mode requête = liste plate serveur : plus de préservation de chemin.
    expect(screen.queryByText('Feature 1')).not.toBeInTheDocument()
    expect(screen.queryByText('Epic 1')).not.toBeInTheDocument()
    expect(screen.queryByText('Story in-progress')).not.toBeInTheDocument()
    // Le mode requête masque le bouton arbre/liste (flat forcé) et affiche la pagination.
    expect(screen.queryByTestId('toggle-view-btn')).not.toBeInTheDocument()
    expect(screen.getByTestId('query-pagination')).toBeInTheDocument()
    expect(screen.queryByTestId('browse-pagination')).not.toBeInTheDocument()

    // Effacer la requête revient en mode browse (arbre complet, sans appel serveur supplémentaire).
    fireEvent.click(screen.getByTestId('query-clear-btn'))
    await waitFor(() => {
      expect(screen.getByText('Epic 1')).toBeInTheDocument()
      expect(screen.getByText('Story in-progress')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('query-pagination')).not.toBeInTheDocument()
    expect(screen.getByTestId('browse-pagination')).toBeInTheDocument()
  })

  it('clicking the title header toggles sort and switches to query mode (asc → desc → none)', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([])
    vi.mocked(docsApi.queryBlockDocuments).mockResolvedValue({
      block_slug: 'b1',
      page: 1,
      page_size: 100,
      total: 1,
      has_next: false,
      objects: [{ id: 'e1', title: 'Epic 1', functional_type_slug: 'epic', properties: [] }],
    })

    renderList()
    await waitFor(() => expect(screen.getByTestId('documents-table')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Titre'))
    await waitFor(() =>
      expect(docsApi.queryBlockDocuments).toHaveBeenCalledWith('ws', 'b1', {
        filters: [],
        sort: [{ key: 'title', dir: 'asc' }],
        projection: null,
        page: 1,
        page_size: 100,
      }),
    )
    // Attendre la fin du fetch (la ligne réapparaît) avant de recliquer, sinon
    // l'entête disparaît pendant le chargement (état "Aucun résultat").
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())

    fireEvent.click(screen.getByText(/Titre/))
    await waitFor(() =>
      expect(docsApi.queryBlockDocuments).toHaveBeenLastCalledWith('ws', 'b1', {
        filters: [],
        sort: [{ key: 'title', dir: 'desc' }],
        projection: null,
        page: 1,
        page_size: 100,
      }),
    )
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())

    fireEvent.click(screen.getByText(/Titre/))
    await waitFor(() => expect(screen.queryByTestId('query-pagination')).not.toBeInTheDocument())
  })

  it('paginates in query mode via the top prev/next controls', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue(makeTreePage(docs))
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([])
    vi.mocked(docsApi.queryBlockDocuments).mockResolvedValue({
      block_slug: 'b1',
      page: 1,
      page_size: 100,
      total: 250,
      has_next: true,
      objects: [{ id: 'e1', title: 'Epic 1', functional_type_slug: 'epic', properties: [] }],
    })

    renderList()
    await waitFor(() => expect(screen.getByTestId('documents-table')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Titre'))
    await waitFor(() => expect(screen.getByText('Epic 1')).toBeInTheDocument())
    expect(screen.getByTestId('query-page-prev')).toBeDisabled()
    expect(screen.getByTestId('query-page-next')).not.toBeDisabled()

    fireEvent.click(screen.getByTestId('query-page-next'))
    await waitFor(() =>
      expect(docsApi.queryBlockDocuments).toHaveBeenLastCalledWith('ws', 'b1', {
        filters: [],
        sort: [{ key: 'title', dir: 'asc' }],
        projection: null,
        page: 2,
        page_size: 100,
      }),
    )
  })

  // US Barre de pagination en haut (≤100 par page) — mode browse (racines).
  it('paginates in browse mode via the top prev/next controls, calling list_block_tree', async () => {
    const docs = [makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' })]
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue(docs)
    vi.mocked(docsApi.getBlockTree).mockResolvedValue({
      block_slug: 'b1',
      page: 1,
      page_size: 100,
      total: 250,
      has_next: true,
      roots: docs.map((d) => ({
        id: d.doc_technical_key,
        title: d.title,
        functional_type_slug: d.functional_type_slug,
        parent_id: d.parent_id,
        properties: [],
        children: [],
      })),
    })
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([])

    renderList()
    await waitFor(() => expect(screen.getByTestId('browse-pagination')).toBeInTheDocument())
    expect(screen.getByTestId('browse-page-prev')).toBeDisabled()
    expect(screen.getByTestId('browse-page-next')).not.toBeDisabled()

    fireEvent.click(screen.getByTestId('browse-page-next'))
    await waitFor(() => expect(docsApi.getBlockTree).toHaveBeenLastCalledWith('ws', 'b1', 2, 100))
    expect(screen.getByTestId('browse-page-prev')).not.toBeDisabled()
  })
})

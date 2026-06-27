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
      getBlockValues: vi.fn(),
      getAllowedTypes: vi.fn(),
      createDocument: vi.fn(),
    },
  }
})

import { docsApi, type DocumentOut, type FunctionalTypeRich } from '../lib/api'
import { BlockDocumentList } from '../pages/BlockDocumentList'

function makeDoc(over: Partial<DocumentOut>): DocumentOut {
  return {
    doc_technical_key: 'd1',
    title: 'Doc',
    type: 'page',
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

const emptyTypesRich: FunctionalTypeRich[] = []
const emptyBlockValues = {}

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
    vi.mocked(docsApi.getBlockValues).mockResolvedValue(emptyBlockValues)
  })

  // DoD 26.1 — état vide
  it('shows empty state', async () => {
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([])
    renderList()
    await waitFor(() => expect(screen.getByText('Aucun document')).toBeInTheDocument())
  })

  // DoD 26.2 — arbre indenté + toggle
  it('renders a tree of documents', async () => {
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([
      makeDoc({ doc_technical_key: 'parent', title: 'Parent', parent_id: null }),
      makeDoc({ doc_technical_key: 'child', title: 'Child', parent_id: 'parent' }),
    ])
    renderList()
    await waitFor(() => expect(screen.getByTestId('documents-table')).toBeInTheDocument())
    expect(screen.getByText('Parent')).toBeInTheDocument()
    expect(screen.getByTestId('add-root-btn')).toBeInTheDocument()
  })

  // DoD 26.3 — colonnes dynamiques : budget_jours présent sur epic, absent sur feature
  it('shows dynamic property column with value for epic, empty for feature', async () => {
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([
      makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' }),
      makeDoc({
        doc_technical_key: 'f1',
        title: 'Feature 1',
        functional_type_slug: 'feature',
        parent_id: 'e1',
      }),
    ])
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([
      {
        id: 'tid-epic',
        slug: 'epic',
        label: 'Epic',
        parent_slug: null,
        workspace_slug: 'ws',
        created_at: '',
        updated_at: '',
        properties: [
          {
            slug: 'budget_jours',
            label: 'Budget (jours)',
            type: 'int',
            default_value: null,
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
        created_at: '',
        updated_at: '',
        properties: [],
      },
    ])
    vi.mocked(docsApi.getBlockValues).mockResolvedValue({
      e1: [
        {
          prop_slug: 'budget_jours',
          prop_type: 'int',
          value: '10',
          allowed_value_slug: null,
          allowed_value_label: null,
          allowed_value_color: null,
        },
      ],
    })
    renderList()
    await waitFor(() => expect(screen.getByText('Budget (jours)')).toBeInTheDocument())
    // Epic a la valeur
    expect(screen.getByText('10')).toBeInTheDocument()
  })

  // DoD 26.3 — dropdown colonnes
  it('opens column visibility dropdown', async () => {
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([
      makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', functional_type_slug: 'epic' }),
    ])
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([
      {
        id: 'tid',
        slug: 'epic',
        label: 'Epic',
        parent_slug: null,
        workspace_slug: 'ws',
        created_at: '',
        updated_at: '',
        properties: [
          {
            slug: 'budget_jours',
            label: 'Budget (jours)',
            type: 'int',
            default_value: null,
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
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([
      makeDoc({ doc_technical_key: 'e1', title: 'Epic 1', parent_id: null, functional_type_slug: 'epic' }),
    ])
    // types-rich doit exposer feature comme enfant d'epic pour que le bouton apparaisse
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([
      { id: 't1', slug: 'epic', label: 'Epic', parent_slug: null, workspace_slug: 'ws', created_at: '', updated_at: '', properties: [] },
      { id: 't2', slug: 'feature', label: 'Feature', parent_slug: 'epic', workspace_slug: 'ws', created_at: '', updated_at: '', properties: [] },
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

  // DoD 26.5 — filtre préservant le chemin (client-side)
  it('path-preserving filter: atdd done → atdd + feature + epic visible, story hidden', async () => {
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([
      makeDoc({ doc_technical_key: 'epic1', title: 'Epic 1', functional_type_slug: 'epic', parent_id: null }),
      makeDoc({ doc_technical_key: 'feat1', title: 'Feature 1', functional_type_slug: 'feature', parent_id: 'epic1' }),
      makeDoc({ doc_technical_key: 'atdd1', title: 'ATDD done', functional_type_slug: 'atdd', parent_id: 'feat1' }),
      makeDoc({ doc_technical_key: 'story1', title: 'Story in-progress', functional_type_slug: 'story', parent_id: 'feat1' }),
    ])
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([
      {
        id: 'tid-atdd',
        slug: 'atdd',
        label: 'ATDD',
        parent_slug: 'feature',
        workspace_slug: 'ws',
        created_at: '',
        updated_at: '',
        properties: [
          {
            slug: 'statut',
            label: 'Statut',
            type: 'restricted_list',
            default_value: null,
            required: false,
            allowed_values: [
              { slug: 'done', label: 'Terminé', position: 1, color: '#22c55e' },
              { slug: 'in-progress', label: 'En cours', position: 0, color: '#f59e0b' },
            ],
          },
        ],
      },
    ])
    vi.mocked(docsApi.getBlockValues).mockResolvedValue({
      atdd1: [
        {
          prop_slug: 'statut',
          prop_type: 'restricted_list',
          value: null,
          allowed_value_slug: 'done',
          allowed_value_label: 'Terminé',
          allowed_value_color: '#22c55e',
        },
      ],
      story1: [
        {
          prop_slug: 'statut',
          prop_type: 'restricted_list',
          value: null,
          allowed_value_slug: 'in-progress',
          allowed_value_label: 'En cours',
          allowed_value_color: '#f59e0b',
        },
      ],
    })

    renderList()
    await waitFor(() => expect(screen.getByTestId('filter-statut')).toBeInTheDocument())

    // Sélectionner le filtre statut=done
    fireEvent.change(screen.getByTestId('filter-statut'), { target: { value: 'done' } })

    await waitFor(() => {
      expect(screen.getByText('ATDD done')).toBeInTheDocument()
      expect(screen.getByText('Feature 1')).toBeInTheDocument()
      expect(screen.getByText('Epic 1')).toBeInTheDocument()
      expect(screen.queryByText('Story in-progress')).not.toBeInTheDocument()
    })
  })
})

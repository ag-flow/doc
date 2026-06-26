import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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
      getAllowedTypes: vi.fn(),
      createDocument: vi.fn(),
    },
  }
})

import { docsApi, type DocumentOut } from '../lib/api'
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
    created_at: '',
    updated_at: '',
    ...over,
  }
}

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/workspaces/ws/blocks/b1']}>
        <Routes>
          <Route path="/workspaces/:ws/blocks/:block" element={<BlockDocumentList />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BlockDocumentList', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows empty state', async () => {
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([])
    renderList()
    await waitFor(() => expect(screen.getByText('Aucun document')).toBeInTheDocument())
  })

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
})

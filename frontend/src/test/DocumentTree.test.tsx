import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  getToken: vi.fn(() => 'tok'),
  setToken: vi.fn(),
  clearToken: vi.fn(),
}))

import { api } from '../lib/api'
import { DocumentTree } from '../pages/DocumentTree'

function renderWithProviders(ws = 'my-ws') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/workspaces/${ws}/documents`]}>
        <Routes>
          <Route path="/workspaces/:ws/documents" element={<DocumentTree />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DocumentTree', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows empty state when no documents', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderWithProviders()
    await waitFor(() => expect(screen.getByText('Aucun document')).toBeInTheDocument())
  })

  it('renders documents from API', async () => {
    vi.mocked(api.get).mockResolvedValue([
      { doc_technical_key: 'uuid-1', title: 'Ma page', parent_id: null },
    ])
    renderWithProviders()
    await waitFor(() => expect(screen.getByTestId('documents-list')).toBeInTheDocument())
    expect(screen.getByText('Ma page')).toBeInTheDocument()
  })

  it('shows create button after load', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderWithProviders()
    await waitFor(() => expect(screen.getByTestId('create-doc-btn')).toBeInTheDocument())
  })
})

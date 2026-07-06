import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
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
import { TypesAdmin } from '../pages/TypesAdmin'

function renderWithProviders(ws = 'my-ws') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/ws/${ws}/types`]}>
        <Routes>
          <Route path="/ws/:wsSlug/types" element={<TypesAdmin />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TypesAdmin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders types from API', async () => {
    vi.mocked(api.get).mockResolvedValue([
      { slug: 'epic', label: 'Epic', parent_slug: null, id: '1' },
    ])
    renderWithProviders()
    await waitFor(() => expect(screen.getByTestId('types-table')).toBeInTheDocument())
    expect(screen.getByText('epic')).toBeInTheDocument()
    expect(screen.getByText('Epic')).toBeInTheDocument()
  })

  it('shows create button after load', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderWithProviders()
    await waitFor(() => expect(screen.getByTestId('create-type-btn')).toBeInTheDocument())
  })

  it('shows the template slug alongside its label in the import dropdown', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/templates') {
        return Promise.resolve([
          { template: 'agile-project', label: 'Projet agile', version: 2, path: '', concrete_types: 0, type_slugs: [] },
        ])
      }
      return Promise.resolve([])
    })
    renderWithProviders()
    await waitFor(() => expect(screen.getByTestId('import-template-btn')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('import-template-btn'))
    await waitFor(() =>
      expect(screen.getByText('Projet agile (v2) — agile-project')).toBeInTheDocument(),
    )
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    api: { ...actual.api, get: vi.fn() },
    docsApi: {
      ...actual.docsApi,
      getBlocks: vi.fn(),
      setBlockExposed: vi.fn(),
      deleteBlock: vi.fn(),
    },
    referencesApi: {
      ...actual.referencesApi,
      getBrokenLinks: vi.fn(),
      getBrokenLinksDetail: vi.fn(),
    },
  }
})

import { api, docsApi, referencesApi, ApiError, type DataBlockOut } from '../lib/api'
import { BlocsAdmin } from '../pages/BlocsAdmin'

function makeBloc(over: Partial<DataBlockOut>): DataBlockOut {
  return {
    id: 'b1',
    slug: 'mon-bloc',
    label: 'Mon bloc',
    functional_type_slug: 'epic',
    parent_slug: null,
    workspace_slug: 'ws',
    exposed: false,
    created_at: '',
    updated_at: '',
    ...over,
  }
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/ws/ws/blocs']}>
        <Routes>
          <Route path="/ws/:wsSlug/blocs" element={<BlocsAdmin />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BlocsAdmin — suppression de bloc', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(referencesApi.getBrokenLinks).mockResolvedValue([])
    vi.mocked(referencesApi.getBrokenLinksDetail).mockResolvedValue([])
  })

  it('supprime un bloc vide après confirmation', async () => {
    vi.mocked(docsApi.getBlocks).mockResolvedValue([makeBloc({})])
    vi.mocked(docsApi.deleteBlock).mockResolvedValue(undefined)

    renderPage()
    fireEvent.click(await screen.findByTestId('delete-bloc-mon-bloc'))
    // Confirmation initiale visible.
    expect(await screen.findByTestId('delete-bloc-dialog')).toBeTruthy()

    fireEvent.click(screen.getByTestId('delete-bloc-confirm'))
    await waitFor(() =>
      expect(docsApi.deleteBlock).toHaveBeenCalledWith('ws', 'mon-bloc', false),
    )
  })

  it('affiche le décompte des dépendants puis supprime en cascade', async () => {
    vi.mocked(docsApi.getBlocks).mockResolvedValue([makeBloc({})])
    // 1er appel (confirm=false) → 409 avec décompte ; 2e (confirm=true) → succès.
    vi.mocked(docsApi.deleteBlock)
      .mockRejectedValueOnce(
        new ApiError(
          409,
          { detail: 'x', dependents: 3, need_confirm: true },
          "détruirait en cascade 1 bloc(s) enfant(s) et 2 document(s)",
        ),
      )
      .mockResolvedValueOnce(undefined)

    renderPage()
    fireEvent.click(await screen.findByTestId('delete-bloc-mon-bloc'))
    fireEvent.click(await screen.findByTestId('delete-bloc-confirm'))

    // Le message de cascade (avec le décompte) apparaît.
    const cascade = await screen.findByTestId('delete-bloc-cascade')
    expect(cascade.textContent).toContain('2 document(s)')
    await waitFor(() =>
      expect(docsApi.deleteBlock).toHaveBeenNthCalledWith(1, 'ws', 'mon-bloc', false),
    )

    // Reconfirmer → suppression cascade assumée.
    fireEvent.click(screen.getByTestId('delete-bloc-confirm'))
    await waitFor(() =>
      expect(docsApi.deleteBlock).toHaveBeenNthCalledWith(2, 'ws', 'mon-bloc', true),
    )
  })
})

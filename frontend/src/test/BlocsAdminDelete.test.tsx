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
      updateBlock: vi.fn(),
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
    documents_count: 0,
    last_write_at: null,
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

describe('BlocsAdmin — table thématisée (Broadsheet)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(referencesApi.getBrokenLinks).mockResolvedValue([])
    vi.mocked(referencesApi.getBrokenLinksDetail).mockResolvedValue([])
  })

  it('la confirmation annonce le nombre de documents concernés', async () => {
    vi.mocked(docsApi.getBlocks).mockResolvedValue([makeBloc({ documents_count: 7 })])
    renderPage()
    fireEvent.click(await screen.findByTestId('delete-bloc-mon-bloc'))
    expect(await screen.findByTestId('delete-bloc-count')).toHaveTextContent('7 documents')
  })

  it('bloc vide : la confirmation le dit au lieu d’annoncer un décompte', async () => {
    vi.mocked(docsApi.getBlocks).mockResolvedValue([makeBloc({ documents_count: 0 })])
    renderPage()
    fireEvent.click(await screen.findByTestId('delete-bloc-mon-bloc'))
    expect(await screen.findByTestId('delete-bloc-count')).toHaveTextContent('vide')
  })

  it('hiérarchie parent/enfant rendue par indentation croissante', async () => {
    vi.mocked(docsApi.getBlocks).mockResolvedValue([
      makeBloc({ slug: 'enfant', label: 'Enfant', parent_slug: 'mon-bloc', id: 'b2' }),
      makeBloc({}),
    ])
    renderPage()
    const parent = await screen.findByTestId('bloc-row-mon-bloc')
    const child = screen.getByTestId('bloc-row-enfant')
    expect(parent.querySelector('td')).toHaveAttribute('data-depth', '0')
    expect(child.querySelector('td')).toHaveAttribute('data-depth', '1')
    // Le parent précède son enfant dans le DOM (ordre d'arbre, pas de création).
    expect(parent.compareDocumentPosition(child) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('liens cassés : 0 en gris, non nul en magenta et dépliable', async () => {
    vi.mocked(docsApi.getBlocks).mockResolvedValue([
      makeBloc({}),
      makeBloc({ slug: 'sain', label: 'Sain', id: 'b3' }),
    ])
    vi.mocked(referencesApi.getBrokenLinks).mockResolvedValue([
      { bloc: 'b1', docs_with_broken_links: 2 },
    ])
    vi.mocked(referencesApi.getBrokenLinksDetail).mockResolvedValue([
      { source_ref: 'd1', source_title: 'Doc A', target_ref: null, target_label: 'Page morte' },
    ])
    renderPage()
    const broken = await screen.findByTestId('broken-links-b1')
    expect(broken).toHaveClass('text-accent-2-700')
    expect(screen.queryByTestId('broken-links-b3')).not.toBeInTheDocument()
    fireEvent.click(broken)
    expect(await screen.findByText(/Page morte/)).toBeInTheDocument()
  })

  it('le drapeau exposé se change sans quitter la liste', async () => {
    vi.mocked(docsApi.getBlocks).mockResolvedValue([makeBloc({ exposed: false })])
    vi.mocked(docsApi.setBlockExposed).mockResolvedValue(makeBloc({ exposed: true }))
    renderPage()
    fireEvent.click(await screen.findByTestId('expose-bloc-mon-bloc'))
    await waitFor(() =>
      expect(docsApi.setBlockExposed).toHaveBeenCalledWith('ws', 'mon-bloc', true),
    )
  })

  it('renommage depuis la liste via l’outil Modifier', async () => {
    vi.mocked(docsApi.getBlocks).mockResolvedValue([makeBloc({})])
    vi.mocked(docsApi.updateBlock).mockResolvedValue(makeBloc({ label: 'Renommé' }))
    renderPage()
    fireEvent.click(await screen.findByTestId('edit-bloc-mon-bloc'))
    const input = await screen.findByLabelText('Libellé')
    fireEvent.change(input, { target: { value: 'Renommé' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() =>
      expect(docsApi.updateBlock).toHaveBeenCalledWith('ws', 'mon-bloc', { label: 'Renommé' }),
    )
  })
})

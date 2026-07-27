import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    api: { get: vi.fn() },
    docsApi: { getBlocks: vi.fn() },
    referencesApi: { searchGlobal: vi.fn() },
  }
})

import { api, docsApi, referencesApi } from '../lib/api'
import { CommandPalette } from '../components/CommandPalette'

function renderPalette(onClose = vi.fn(), path = '/ws/prod/blocs') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={<CommandPalette onClose={onClose} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return onClose
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.get).mockResolvedValue([
    { slug: 'prod', label: 'Documentation produit' },
  ] as never)
  vi.mocked(docsApi.getBlocks).mockResolvedValue([
    { id: 'b1', slug: 'specs', label: 'Spécifications', functional_type_slug: 'epic' },
  ] as never)
  vi.mocked(referencesApi.searchGlobal).mockResolvedValue([])
})

describe('CommandPalette', () => {
  it('résultats groupés, correspondance surlignée en cyan', async () => {
    renderPalette()
    fireEvent.change(screen.getByTestId('palette-input'), { target: { value: 'spé' } })
    await waitFor(() => expect(screen.getByText('Blocs')).toBeInTheDocument())
    const mark = document.querySelector('mark')
    expect(mark).toHaveTextContent(/spé/i)
    expect(mark).toHaveClass('bg-accent-200')
  })

  it('navigation clavier : flèches + Entrée ouvrent le résultat actif', async () => {
    const onClose = renderPalette()
    const input = screen.getByTestId('palette-input')
    fireEvent.change(input, { target: { value: 'produit' } })
    await waitFor(() => expect(screen.getByText('Workspaces')).toBeInTheDocument())
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onClose).toHaveBeenCalled()
  })

  it('recherche documents sur tous les workspaces accessibles, chemin en indice', async () => {
    vi.mocked(referencesApi.searchGlobal).mockResolvedValue([
      { id: 'd1', title: 'Socle CSS', type: 'feature', workspace_slug: 'autre-ws', block_slug: 'specs' },
    ])
    renderPalette()
    fireEvent.change(screen.getByTestId('palette-input'), { target: { value: 'socle' } })
    await waitFor(() =>
      expect(referencesApi.searchGlobal).toHaveBeenCalledWith('socle', 8),
    )
    // Le titre est découpé par le surlignage : on vérifie l'item entier ; le
    // chemin pointe vers le workspace du RÉSULTAT, pas le courant.
    const hint = await screen.findByText('autre-ws › specs')
    expect(hint.closest('button')).toHaveTextContent('Socle CSS')
  })

  it('état vide explicite, jamais une liste blanche', async () => {
    renderPalette()
    fireEvent.change(screen.getByTestId('palette-input'), { target: { value: 'zzzzzz' } })
    const empty = await screen.findByTestId('palette-empty')
    expect(empty).toHaveTextContent('Aucun résultat pour « zzzzzz »')
  })

  it('Échap ferme la palette', async () => {
    const onClose = renderPalette()
    fireEvent.keyDown(screen.getByTestId('palette-input'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

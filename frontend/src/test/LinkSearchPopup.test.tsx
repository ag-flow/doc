/** Sélecteur de document lié (`docflow://doc/…`) — épic MLD F4c.
 *
 *  Tests de CARACTÉRISATION : écrits sur le comportement existant AVANT
 *  l'extraction de la logique en service headless, pour que le refactor soit
 *  vérifiable. Ils doivent rester verts sans modification après extraction.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LinkSearchPopup } from '../components/LinkSearchPopup'
import { referencesApi, type DocumentSearchResult } from '../lib/api'

vi.mock('../lib/api', () => ({
  referencesApi: { searchDocuments: vi.fn() },
  api: { get: vi.fn().mockResolvedValue([]) },
}))

const RESULTS: DocumentSearchResult[] = [
  { id: 'a1', title: 'Architecture', type: 'epic', bloc: 'b1' },
  { id: 'b2', title: 'Backlog', type: 'feature', bloc: 'b1' },
]

function renderPopup(onSelect = vi.fn(), onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <LinkSearchPopup wsSlug="ws" onSelect={onSelect} onClose={onClose} />
    </QueryClientProvider>,
  )
  return { onSelect, onClose }
}

beforeEach(() => {
  vi.mocked(referencesApi.searchDocuments).mockResolvedValue(RESULTS)
})

describe('LinkSearchPopup — recherche', () => {
  it('ne cherche pas tant que la saisie est vide', () => {
    renderPopup()
    expect(referencesApi.searchDocuments).not.toHaveBeenCalled()
    expect(screen.getByText(/Tapez pour rechercher/)).toBeInTheDocument()
  })

  it('cherche dans le workspace courant et affiche les résultats', async () => {
    renderPopup()
    await userEvent.type(screen.getByRole('textbox'), 'arch')

    await waitFor(() =>
      expect(referencesApi.searchDocuments).toHaveBeenCalledWith('ws', 'arch'),
    )
    expect(await screen.findByText('Architecture')).toBeInTheDocument()
    expect(screen.getByText('Backlog')).toBeInTheDocument()
  })

  it('débounce la frappe : cherche la saisie finale, pas chaque caractère', async () => {
    renderPopup()
    await userEvent.type(screen.getByRole('textbox'), 'archi')

    // On attend l'appel portant la saisie COMPLÈTE — c'est le contrat visible :
    // ce que l'utilisateur a tapé est ce qui est cherché.
    await waitFor(() =>
      expect(referencesApi.searchDocuments).toHaveBeenCalledWith('ws', 'archi'),
    )
    // Et le debounce a bien coalescé : moins d'appels que de caractères frappés.
    expect(vi.mocked(referencesApi.searchDocuments).mock.calls.length).toBeLessThan(5)
  })

  it('annonce l\'absence de résultat', async () => {
    vi.mocked(referencesApi.searchDocuments).mockResolvedValue([])
    renderPopup()
    await userEvent.type(screen.getByRole('textbox'), 'zzz')

    expect(await screen.findByText(/Aucun document trouvé/)).toBeInTheDocument()
  })

  it('ne casse pas quand la recherche échoue', async () => {
    vi.mocked(referencesApi.searchDocuments).mockRejectedValue(new Error('réseau'))
    renderPopup()
    await userEvent.type(screen.getByRole('textbox'), 'arch')

    expect(await screen.findByText(/Aucun document trouvé/)).toBeInTheDocument()
  })
})

describe('LinkSearchPopup — sélection', () => {
  it('remonte le document choisi au clic', async () => {
    const { onSelect } = renderPopup()
    await userEvent.type(screen.getByRole('textbox'), 'arch')

    await userEvent.click(await screen.findByText('Architecture'))
    expect(onSelect).toHaveBeenCalledWith(RESULTS[0])
  })

  it('remonte le premier résultat sur Entrée', async () => {
    const { onSelect } = renderPopup()
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'arch')
    await screen.findByText('Architecture')

    await userEvent.type(input, '{Enter}')
    expect(onSelect).toHaveBeenCalledWith(RESULTS[0])
  })

  it('descend la sélection avec la flèche bas', async () => {
    const { onSelect } = renderPopup()
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'arch')
    await screen.findByText('Architecture')

    await userEvent.type(input, '{ArrowDown}{Enter}')
    expect(onSelect).toHaveBeenCalledWith(RESULTS[1])
  })

  it('ne descend pas au-delà du dernier résultat', async () => {
    const { onSelect } = renderPopup()
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'arch')
    await screen.findByText('Architecture')

    await userEvent.type(input, '{ArrowDown}{ArrowDown}{ArrowDown}{Enter}')
    expect(onSelect).toHaveBeenCalledWith(RESULTS[1])
  })

  it('ne remonte pas au-dessus du premier résultat', async () => {
    const { onSelect } = renderPopup()
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'arch')
    await screen.findByText('Architecture')

    await userEvent.type(input, '{ArrowUp}{ArrowUp}{Enter}')
    expect(onSelect).toHaveBeenCalledWith(RESULTS[0])
  })

  it('ferme sur Échap', async () => {
    const { onClose } = renderPopup()
    await userEvent.type(screen.getByRole('textbox'), '{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})

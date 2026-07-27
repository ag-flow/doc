import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    inviteApi: { info: vi.fn(), accept: vi.fn() },
  }
})

import { inviteApi } from '../lib/api'
import { InvitePage } from '../pages/InvitePage'

function renderPage(token = 'tok-123') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/invite/${token}`]}>
        <Routes>
          <Route path="/invite/:token" element={<InvitePage />} />
          <Route path="/login" element={<p>page login</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(inviteApi.info).mockResolvedValue({ email: 'n@example.com', label: 'Nouvelle' })
})

describe('InvitePage (écart n°7)', () => {
  it('affiche l’invité et accepte avec un mot de passe confirmé', async () => {
    vi.mocked(inviteApi.accept).mockResolvedValue(undefined)
    renderPage()
    expect(await screen.findByText('Bienvenue, Nouvelle')).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('invite-password'), {
      target: { value: 'mot-de-passe-solide' },
    })
    fireEvent.change(screen.getByTestId('invite-confirm'), {
      target: { value: 'mot-de-passe-solide' },
    })
    fireEvent.click(screen.getByTestId('invite-submit'))
    await waitFor(() =>
      expect(inviteApi.accept).toHaveBeenCalledWith('tok-123', 'mot-de-passe-solide'),
    )
    expect(await screen.findByText('page login')).toBeInTheDocument()
  })

  it('mots de passe divergents → erreur locale, aucun appel', async () => {
    renderPage()
    await screen.findByText('Bienvenue, Nouvelle')
    fireEvent.change(screen.getByTestId('invite-password'), {
      target: { value: 'mot-de-passe-solide' },
    })
    fireEvent.change(screen.getByTestId('invite-confirm'), { target: { value: 'autre-chose-xx' } })
    fireEvent.click(screen.getByTestId('invite-submit'))
    expect(await screen.findByRole('alert')).toHaveTextContent('ne correspondent pas')
    expect(inviteApi.accept).not.toHaveBeenCalled()
  })

  it('jeton invalide → message unique, sans oracle', async () => {
    vi.mocked(inviteApi.info).mockRejectedValue(new Error('404'))
    renderPage('mauvais')
    expect(await screen.findByTestId('invite-invalid')).toHaveTextContent('inconnu, déjà utilisé ou expiré')
  })
})

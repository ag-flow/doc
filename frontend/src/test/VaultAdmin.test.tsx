import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    isSuperAdmin: () => true,
    vaultApi: {
      listWallets: vi.fn(),
      createWallet: vi.fn(),
      checkWallet: vi.fn(),
      deleteWallet: vi.fn(),
      connectStart: vi.fn(),
    },
    secretsApi: {
      ...actual.secretsApi,
      list: vi.fn(),
    },
  }
})

import { vaultApi, secretsApi } from '../lib/api'
import { VaultAdmin } from '../pages/VaultAdmin'

/** Sonde : expose la recherche d'URL courante du routeur, pour vérifier le
 *  nettoyage du paramètre ?connect= sans dépendre de window.location (que
 *  MemoryRouter ne synchronise pas). */
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-probe">{location.search}</div>
}

function renderPage(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const spy = vi.spyOn(qc, 'invalidateQueries')
  const utils = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <LocationProbe />
        <Routes>
          <Route path="/admin/vault" element={<VaultAdmin />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...utils, invalidateSpy: spy }
}

describe('VaultAdmin — résultat au retour de Harpocrate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(vaultApi.listWallets).mockResolvedValue([])
    vi.mocked(secretsApi.list).mockResolvedValue([])
  })

  it('connect=ok → message de succès et refetch des listes concernées', async () => {
    const { invalidateSpy } = renderPage('/admin/vault?connect=ok')

    await waitFor(() => expect(screen.getByTestId('vault-connect-message')).toBeInTheDocument())
    expect(screen.getByTestId('vault-connect-message').textContent).toMatch(/connect/i)

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['harpocrate-keys'] }),
      ),
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['vault-wallets'] }),
    )
  })

  it.each([
    ['denied', /refusée/i],
    ['invalid_state', /invalide ou expiré/i],
    ['already', /déjà traitée/i],
    ['duplicate', /déjà cet alias/i],
    ['error', /échec/i],
  ])('connect=%s → message correspondant', async (outcome, expected) => {
    renderPage(`/admin/vault?connect=${outcome}`)

    await waitFor(() => expect(screen.getByTestId('vault-connect-message')).toBeInTheDocument())
    expect(screen.getByTestId('vault-connect-message').textContent).toMatch(expected)
  })

  it('ne montre jamais de token, et nettoie le paramètre après lecture', async () => {
    renderPage('/admin/vault?connect=ok')

    await waitFor(() => expect(screen.getByTestId('vault-connect-message')).toBeInTheDocument())
    expect(document.body.textContent).not.toMatch(/eyJ|Bearer |token=/i)

    await waitFor(() =>
      expect(screen.getByTestId('location-probe').textContent).not.toContain('connect='),
    )
  })

  it('sans paramètre connect, aucun message ne s’affiche', async () => {
    renderPage('/admin/vault')
    await waitFor(() => expect(screen.getByTestId('tab-wallets')).toBeInTheDocument())
    expect(screen.queryByTestId('vault-connect-message')).not.toBeInTheDocument()
  })
})

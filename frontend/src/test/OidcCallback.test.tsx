import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import '../lib/i18n'
import { OidcCallback } from '../pages/OidcCallback'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('../lib/api', () => ({
  setToken: vi.fn(),
  getToken: vi.fn(() => null),
  clearToken: vi.fn(),
}))

vi.mock('../lib/oidcClient', () => ({
  completeOidcCallback: vi.fn(),
}))

import { setToken } from '../lib/api'
import { completeOidcCallback } from '../lib/oidcClient'

describe('OidcCallback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('stores the token and navigates home on success', async () => {
    vi.mocked(completeOidcCallback).mockResolvedValue('tok-oidc')
    render(
      <MemoryRouter>
        <OidcCallback />
      </MemoryRouter>,
    )
    await waitFor(() => expect(setToken).toHaveBeenCalledWith('tok-oidc'))
    expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
  })

  it('shows the pending-validation message on PendingValidation', async () => {
    vi.mocked(completeOidcCallback).mockRejectedValue(
      Object.assign(new Error('PendingValidation'), { detail: 'PendingValidation' }),
    )
    render(
      <MemoryRouter>
        <OidcCallback />
      </MemoryRouter>,
    )
    await waitFor(() =>
      expect(
        screen.getByText('Votre compte est en attente de validation par un administrateur.'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByTestId('back-to-login')).toBeInTheDocument()
    expect(setToken).not.toHaveBeenCalled()
  })

  it('shows an error message on flow failure', async () => {
    vi.mocked(completeOidcCallback).mockRejectedValue(new Error('state OIDC absent ou invalide'))
    render(
      <MemoryRouter>
        <OidcCallback />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByTestId('oidc-error')).toBeInTheDocument())
    expect(setToken).not.toHaveBeenCalled()
  })
})

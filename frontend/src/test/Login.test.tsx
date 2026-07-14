import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import '../lib/i18n'
import { Login } from '../pages/Login'

// Mock navigation
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

// Mock api
vi.mock('../lib/api', () => ({
  api: {
    post: vi.fn(),
  },
  setToken: vi.fn(),
  getToken: vi.fn(() => null),
  clearToken: vi.fn(),
  setupApi: {
    methods: vi.fn(() =>
      Promise.resolve({ local: true, oidc: false, needs_setup: false })
    ),
    initAdmin: vi.fn(),
  },
}))

// Mock du flow OIDC : la redirection navigateur n'est pas testable en jsdom
vi.mock('../lib/oidcClient', () => ({
  beginOidcLogin: vi.fn(() => Promise.resolve()),
}))

import { api, setToken, setupApi } from '../lib/api'
import { beginOidcLogin } from '../lib/oidcClient'

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders login form', async () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )
    // Login rend null tant que /auth/methods n'a pas répondu
    expect(await screen.findByTestId('email-input')).toBeInTheDocument()
    expect(screen.getByTestId('password-input')).toBeInTheDocument()
    expect(screen.getByTestId('submit-button')).toBeInTheDocument()
  })

  it('calls api.post on submit and sets token', async () => {
    vi.mocked(api.post).mockResolvedValue({ access_token: 'tok-123' })
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )
    fireEvent.change(await screen.findByTestId('email-input'), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'secret' } })
    fireEvent.click(screen.getByTestId('submit-button'))
    await waitFor(() => expect(setToken).toHaveBeenCalledWith('tok-123'))
    expect(mockNavigate).toHaveBeenCalledWith('/')
  })

  it('shows error on failed login', async () => {
    vi.mocked(api.post).mockRejectedValue(new Error('bad credentials'))
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )
    fireEvent.change(await screen.findByTestId('email-input'), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByTestId('submit-button'))
    await waitFor(() => expect(screen.getByText('Identifiants invalides')).toBeInTheDocument())
  })

  it('hides the OIDC button when /auth/methods says oidc=false', async () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )
    await screen.findByTestId('email-input')
    expect(screen.queryByTestId('oidc-button')).not.toBeInTheDocument()
  })

  it('shows the OIDC button when /auth/methods says oidc=true and starts the flow', async () => {
    vi.mocked(setupApi.methods).mockResolvedValue({
      local: true,
      oidc: true,
      needs_setup: false,
    })
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )
    const button = await screen.findByTestId('oidc-button')
    fireEvent.click(button)
    await waitFor(() => expect(beginOidcLogin).toHaveBeenCalledTimes(1))
  })
  it('hides the local form and shows a notice when local login is disabled', async () => {
    vi.mocked(setupApi.methods).mockResolvedValue({
      local: false,
      oidc: true,
      needs_setup: false,
    })
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )
    expect(await screen.findByTestId('local-disabled-notice')).toBeInTheDocument()
    expect(screen.queryByTestId('email-input')).not.toBeInTheDocument()
    expect(screen.getByTestId('oidc-button')).toBeInTheDocument()
  })
})

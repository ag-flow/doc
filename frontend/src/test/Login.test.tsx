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

import { api, setToken } from '../lib/api'

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
})

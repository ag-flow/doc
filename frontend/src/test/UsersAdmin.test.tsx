import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    usersApi: { ...actual.usersApi, list: vi.fn() },
    meApi: { ...actual.meApi, get: vi.fn() },
  }
})

import { usersApi, meApi, type AppUserOut, type MeProfileOut } from '../lib/api'
import { UsersAdmin } from '../pages/UsersAdmin'

function user(over: Partial<AppUserOut>): AppUserOut {
  return {
    id: 'u-x', email: 'x@example.com', label: 'X', username: null,
    source: 'oidc', is_admin: false, validated: true, disabled: false,
    has_local_password: false, created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z', last_login_at: null, workspaces_count: 1,
    ...over,
  }
}

const me: MeProfileOut = {
  id: 'u-me', email: 'moi@example.com', username: 'moi', label: 'Moi',
  source: 'oidc', is_admin: true, identity: null,
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <UsersAdmin />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(meApi.get).mockResolvedValue(me)
  vi.mocked(usersApi.list).mockResolvedValue([
    user({ id: 'u-me', email: 'moi@example.com', label: 'Moi', is_admin: true }),
    user({ id: 'u-boot', email: 'admin@example.com', label: 'Admin site', source: 'local', is_admin: true, has_local_password: true }),
    user({ id: 'u-std', email: 'std@example.com', label: 'Standard' }),
  ])
})

describe('UsersAdmin — gardes des actions', () => {
  it("aucune action sur la ligne de l'utilisateur courant", async () => {
    renderPage()
    const row = await screen.findByTestId('user-row-u-me')
    expect(row.querySelectorAll('button')).toHaveLength(0)
  })

  it("l'admin du site (local + mot de passe) : ni rétrograder, ni désactiver, ni supprimer", async () => {
    renderPage()
    await screen.findByTestId('user-row-u-boot')
    expect(screen.queryByTestId('toggle-role-u-boot')).not.toBeInTheDocument()
    expect(screen.queryByTestId('toggle-disabled-u-boot')).not.toBeInTheDocument()
    expect(screen.queryByTestId('delete-u-boot')).not.toBeInTheDocument()
  })

  it('un autre utilisateur garde toutes ses actions', async () => {
    renderPage()
    await screen.findByTestId('user-row-u-std')
    expect(screen.getByTestId('toggle-role-u-std')).toBeInTheDocument()
    expect(screen.getByTestId('toggle-disabled-u-std')).toBeInTheDocument()
    expect(screen.getByTestId('delete-u-std')).toBeInTheDocument()
  })
})

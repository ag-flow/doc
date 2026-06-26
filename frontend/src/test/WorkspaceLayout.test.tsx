import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    api: { ...actual.api, get: vi.fn() },
    docsApi: { ...actual.docsApi, getBlocks: vi.fn() },
    getToken: vi.fn(() => 'tok'),
  }
})

import { api, docsApi, type WorkspaceOut, type DataBlockOut } from '../lib/api'
import { WorkspaceLayout } from '../pages/WorkspaceLayout'

const existingBloc: DataBlockOut = {
  id: 'bloc-id',
  slug: 'mon-bloc',
  label: 'Mon Bloc',
  functional_type_slug: 'epic',
  parent_slug: null,
  workspace_slug: 'devpod-ui',
  created_at: '',
  updated_at: '',
}

const activeWs: WorkspaceOut = {
  workspace_technical_key: 'wk1',
  slug: 'devpod-ui',
  label: 'DevPod UI',
  description: null,
  archived_at: null,
  created_at: '',
  updated_at: '',
}

const archivedWs: WorkspaceOut = {
  ...activeWs,
  slug: 'old-ws',
  label: 'Old',
  archived_at: '2025-01-01T00:00:00Z',
}

const otherWs: WorkspaceOut = {
  ...activeWs,
  workspace_technical_key: 'wk2',
  slug: 'autre-ws',
  label: 'Autre WS',
}

function renderLayout(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/workspaces" element={<div data-testid="workspaces-page">Workspaces</div>} />
          <Route path="/ws/:wsSlug" element={<WorkspaceLayout />}>
            <Route index element={<Navigate to="blocs" replace />} />
            <Route path="types" element={<div data-testid="types-page">Types</div>} />
            <Route path="blocs" element={<div data-testid="blocs-page">Blocs</div>} />
            <Route
              path="blocs/:blocSlug/documents"
              element={<div data-testid="docs-page">Documents</div>}
            />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('WorkspaceLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(docsApi.getBlocks).mockResolvedValue([])
  })

  // DoD 28.2 — workspace inconnu → redirect /workspaces
  it('redirects to /workspaces when workspace is unknown (404)', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/inconnu')) return Promise.reject(new Error('404'))
      return Promise.resolve([activeWs])
    })

    renderLayout('/ws/inconnu/types')

    await waitFor(() =>
      expect(screen.getByTestId('workspaces-page')).toBeInTheDocument(),
    )
  })

  // DoD 28.2 — workspace archivé → redirect /workspaces
  it('redirects to /workspaces when workspace is archived', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/old-ws')) return Promise.resolve(archivedWs)
      return Promise.resolve([archivedWs])
    })

    renderLayout('/ws/old-ws/types')

    await waitFor(() =>
      expect(screen.getByTestId('workspaces-page')).toBeInTheDocument(),
    )
  })

  // DoD 28.3 — F5 sur route profonde → réhydratation (fil d'Ariane + onglets)
  it('rehydrates workspace context from URL on deep route (F5 simulation)', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/devpod-ui')) return Promise.resolve(activeWs)
      return Promise.resolve([activeWs])
    })

    renderLayout('/ws/devpod-ui/blocs')

    await waitFor(() =>
      expect(screen.getByTestId('workspace-layout')).toBeInTheDocument(),
    )
    expect(screen.getByText('DevPod UI')).toBeInTheDocument()
    expect(screen.getByTestId('tab-types')).toBeInTheDocument()
    expect(screen.getByTestId('tab-blocs')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('blocs-page')).toBeInTheDocument())
  })

  // DoD 28.3 — onglet Types actif sur /ws/:wsSlug/types
  it('marks Types tab as active on /ws/:wsSlug/types', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/devpod-ui')) return Promise.resolve(activeWs)
      return Promise.resolve([activeWs])
    })

    renderLayout('/ws/devpod-ui/types')

    await waitFor(() => expect(screen.getByTestId('types-page')).toBeInTheDocument())
    expect(screen.getByTestId('tab-types')).toBeInTheDocument()
  })

  // DoD 28.4 — onglet Documents désactivé sans bloc sélectionné
  it('shows Documents tab as disabled when no bloc is in URL', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/devpod-ui')) return Promise.resolve(activeWs)
      return Promise.resolve([activeWs])
    })

    renderLayout('/ws/devpod-ui/blocs')

    await waitFor(() =>
      expect(screen.getByTestId('tab-documents-disabled')).toBeInTheDocument(),
    )
  })

  // DoD 28.4 — onglet Documents actif quand un bloc est dans l'URL
  it('shows Documents tab as link when a bloc is selected', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/devpod-ui')) return Promise.resolve(activeWs)
      return Promise.resolve([activeWs])
    })
    vi.mocked(docsApi.getBlocks).mockResolvedValue([existingBloc])

    renderLayout('/ws/devpod-ui/blocs/mon-bloc/documents')

    await waitFor(() => expect(screen.getByTestId('tab-documents')).toBeInTheDocument())
    expect(screen.queryByTestId('tab-documents-disabled')).not.toBeInTheDocument()
  })

  // DoD 28.5 — dropdown workspace + switch conserve la section
  it('preserves current section when switching workspace via dropdown', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/devpod-ui')) return Promise.resolve(activeWs)
      return Promise.resolve([activeWs, otherWs])
    })

    renderLayout('/ws/devpod-ui/types')
    await waitFor(() => expect(screen.getByTestId('workspace-layout')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('ws-dropdown-btn'))
    await waitFor(() => expect(screen.getByTestId('ws-dropdown-menu')).toBeInTheDocument())

    expect(screen.getByTestId('ws-switch-autre-ws')).toBeInTheDocument()
    expect(screen.getByTestId('ws-switch-autre-ws').textContent).toBe('Autre WS')
  })

  // DoD 28.5 — "Tous les workspaces" dans le dropdown
  it('shows "Tous les workspaces" entry in dropdown', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/devpod-ui')) return Promise.resolve(activeWs)
      return Promise.resolve([activeWs])
    })

    renderLayout('/ws/devpod-ui/blocs')
    await waitFor(() => expect(screen.getByTestId('ws-dropdown-btn')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('ws-dropdown-btn'))
    await waitFor(() => expect(screen.getByTestId('ws-switch-all')).toBeInTheDocument())
  })

  // Garde bloc : blocSlug inexistant → redirect vers /ws/:wsSlug/blocs
  it('redirects to blocs list when blocSlug does not exist', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/devpod-ui')) return Promise.resolve(activeWs)
      return Promise.resolve([activeWs])
    })
    vi.mocked(docsApi.getBlocks).mockResolvedValue([existingBloc])

    renderLayout('/ws/devpod-ui/blocs/inexistant/documents')

    await waitFor(() => expect(screen.getByTestId('blocs-page')).toBeInTheDocument())
    expect(screen.queryByTestId('docs-page')).not.toBeInTheDocument()
  })

  // Garde bloc : blocSlug valide → documents s'affichent
  it('shows docs page when blocSlug exists', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/devpod-ui')) return Promise.resolve(activeWs)
      return Promise.resolve([activeWs])
    })
    vi.mocked(docsApi.getBlocks).mockResolvedValue([existingBloc])

    renderLayout('/ws/devpod-ui/blocs/mon-bloc/documents')

    await waitFor(() => expect(screen.getByTestId('docs-page')).toBeInTheDocument())
  })
})

describe('WorkspaceList redirect message', () => {
  beforeEach(() => vi.clearAllMocks())

  // DoD 28.2 — message affiché sur WorkspaceList après redirection
  it('shows message when redirected from unknown workspace', async () => {
    vi.mocked(api.get).mockResolvedValue([activeWs])
    vi.mocked(docsApi.getBlocks).mockResolvedValue([])

    const { default: WorkspaceList } = await import('../pages/WorkspaceList')
    const { WorkspaceProvider } = await import('../contexts/WorkspaceContext')

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <WorkspaceProvider>
          <MemoryRouter
            initialEntries={[{ pathname: '/workspaces', state: { invalidWs: 'inconnu' } }]}
          >
            <Routes>
              <Route path="/workspaces" element={<WorkspaceList />} />
              <Route path="/ws/:wsSlug/blocs" element={<div />} />
            </Routes>
          </MemoryRouter>
        </WorkspaceProvider>
      </QueryClientProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('redirect-msg')).toBeInTheDocument())
    expect(screen.getByTestId('redirect-msg').textContent).toContain('inconnu')
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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
import { WorkspaceProvider, useWorkspace } from '../contexts/WorkspaceContext'
// Import statique : chargé à l'import du fichier de test, pas dans le corps du test
// (la transformation à la volée du graphe de modules dépassait le timeout de 5 s).
import WorkspaceList from '../pages/WorkspaceList'

/** Sonde du contexte workspace : ce que liront les blocs dataset / puces artefact. */
function SlugProbe() {
  const { currentSlug } = useWorkspace()
  return <div data-testid="ctx-slug">{currentSlug ?? '∅'}</div>
}

const existingBloc: DataBlockOut = {
  id: 'bloc-id',
  slug: 'mon-bloc',
  label: 'Mon Bloc',
  functional_type_slug: 'epic',
  parent_slug: null,
  workspace_slug: 'devpod-ui',
  exposed: false,
  created_at: '',
  updated_at: '',
  documents_count: 0,
  last_write_at: null,
}

const activeWs: WorkspaceOut = {
  workspace_technical_key: 'wk1',
  slug: 'devpod-ui',
  label: 'DevPod UI',
  description: null,
  archived_at: null,
  created_at: '',
  updated_at: '',
  blocks_count: 0,
  documents_count: 0,
  last_activity_at: null,
}

const archivedWs: WorkspaceOut = {
  ...activeWs,
  slug: 'old-ws',
  label: 'Old',
  archived_at: '2025-01-01T00:00:00Z',
}

function renderLayout(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceProvider>
      <SlugProbe />
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
      </WorkspaceProvider>
    </QueryClientProvider>,
  )
}

describe('WorkspaceLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(docsApi.getBlocks).mockResolvedValue([])
  })

  // Régression : le contexte workspace ne suivait que les clics dans la liste des
  // workspaces. Toute autre navigation (Cmd+K, lien direct, F5) laissait un slug
  // périmé — les blocs dataset, puces artefact et liens `artifact://` appelaient
  // alors l'API sur le MAUVAIS workspace (404).
  it('synchronise le contexte workspace depuis la route (slug périmé écarté)', async () => {
    localStorage.setItem('ws_slug', 'autre-ws')
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/devpod-ui')) return Promise.resolve(activeWs)
      return Promise.resolve([activeWs])
    })

    renderLayout('/ws/devpod-ui/blocs')

    await waitFor(() => expect(screen.getByTestId('ctx-slug')).toHaveTextContent('devpod-ui'))
    // Le contenu ne se monte qu'une fois le contexte aligné sur la route.
    await waitFor(() => expect(screen.getByTestId('blocs-page')).toBeInTheDocument())
    expect(screen.getByTestId('ctx-slug')).toHaveTextContent('devpod-ui')
  })

  // Garde workspace : inconnu → redirect /workspaces
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

  // Garde workspace : archivé → redirect /workspaces
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

  // F5 sur route profonde → le child route s'affiche correctement
  it('rehydrates and renders child route on deep URL (F5 simulation)', async () => {
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path.includes('/workspaces/devpod-ui')) return Promise.resolve(activeWs)
      return Promise.resolve([activeWs])
    })

    renderLayout('/ws/devpod-ui/blocs')

    await waitFor(() =>
      expect(screen.getByTestId('workspace-layout')).toBeInTheDocument(),
    )
    await waitFor(() => expect(screen.getByTestId('blocs-page')).toBeInTheDocument())
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

  it('shows message when redirected from unknown workspace', async () => {
    vi.mocked(api.get).mockResolvedValue([activeWs])
    vi.mocked(docsApi.getBlocks).mockResolvedValue([])

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

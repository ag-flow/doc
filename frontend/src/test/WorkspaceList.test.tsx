import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import '../lib/i18n'
import { WorkspaceProvider } from '../contexts/WorkspaceContext'
import WorkspaceList from '../pages/WorkspaceList'
import { api } from '../lib/api'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  }
})

const mockWorkspaces = [
  {
    workspace_technical_key: 'uuid-1',
    slug: 'mon-ws',
    label: 'Mon Workspace',
    description: null,
    archived_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

function wrapper(children: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <WorkspaceProvider>{children}</WorkspaceProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => vi.clearAllMocks())

describe('WorkspaceList', () => {
  it('affiche la liste des workspaces', async () => {
    vi.mocked(api.get).mockResolvedValue(mockWorkspaces)
    render(wrapper(<WorkspaceList />))
    await waitFor(() => expect(screen.getByTestId('ws-row-mon-ws')).toBeInTheDocument())
    expect(screen.getByText('Mon Workspace')).toBeInTheDocument()
  })

  it('affiche le bouton créer', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    render(wrapper(<WorkspaceList />))
    await waitFor(() => expect(screen.getByTestId('create-ws-btn')).toBeInTheDocument())
  })

  it('valide le slug côté client', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    render(wrapper(<WorkspaceList />))
    await waitFor(() => screen.getByTestId('create-ws-btn'))
    fireEvent.click(screen.getByTestId('create-ws-btn'))
    await waitFor(() => screen.getByTestId('slug-input'))
    fireEvent.change(screen.getByTestId('slug-input'), { target: { value: 'INVALID SLUG' } })
    await waitFor(() =>
      expect(screen.getByText(/slug doit commencer/i)).toBeInTheDocument()
    )
  })

  it('affiche la modale de confirmation avant suppression', async () => {
    vi.mocked(api.get).mockResolvedValue(mockWorkspaces)
    render(wrapper(<WorkspaceList />))
    await waitFor(() => screen.getByTestId('delete-ws-mon-ws'))
    fireEvent.click(screen.getByTestId('delete-ws-mon-ws'))
    await waitFor(() => expect(screen.getByTestId('delete-modal')).toBeInTheDocument())
    expect(screen.getByTestId('confirm-delete-btn')).toBeDisabled()
  })

  it('active le bouton suppression uniquement si slug correct', async () => {
    vi.mocked(api.get).mockResolvedValue(mockWorkspaces)
    render(wrapper(<WorkspaceList />))
    await waitFor(() => screen.getByTestId('delete-ws-mon-ws'))
    fireEvent.click(screen.getByTestId('delete-ws-mon-ws'))
    await waitFor(() => screen.getByTestId('delete-confirm-input'))
    fireEvent.change(screen.getByTestId('delete-confirm-input'), { target: { value: 'mon-ws' } })
    await waitFor(() =>
      expect(screen.getByTestId('confirm-delete-btn')).not.toBeDisabled()
    )
  })
})

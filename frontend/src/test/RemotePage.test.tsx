import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    remotePointsApi: {
      list: vi.fn(),
      create: vi.fn(),
      get: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      test: vi.fn(),
    },
    remoteCertsApi: {
      list: vi.fn(),
      create: vi.fn(),
      delete: vi.fn(),
    },
    backupApi: {
      listJobs: vi.fn(),
      listRuns: vi.fn(),
      createJob: vi.fn(),
      updateJob: vi.fn(),
      deleteJob: vi.fn(),
    },
    getToken: vi.fn(() => 'tok'),
  }
})

import { remotePointsApi, remoteCertsApi, backupApi, type RemotePointOut } from '../lib/api'
import { RemotePage } from '../pages/RemotePage'

const pt1: RemotePointOut = {
  id: 'pt-1',
  slug: 'backup-101',
  label: 'Backup-101',
  point_type: 'sftp',
  host: '192.168.10.236',
  port: null,
  username: 'agflow',
  git_provider: null,
  git_repo: null,
  git_branch: 'main',
  auth_type: 'password',
  auth_storage: 'local',
  auth_vault_ref: null,
  certificate_slug: null,
  has_local_secret: true,
  created_at: '',
  updated_at: '',
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/admin/remote']}>
        <RemotePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function openPointsTabAndEdit() {
  renderPage()
  fireEvent.click(screen.getByText('Remote Points'))
  await waitFor(() => expect(screen.getByTestId('edit-point-backup-101')).toBeInTheDocument())
  fireEvent.click(screen.getByTestId('edit-point-backup-101'))
  await waitFor(() => expect(screen.getByTestId('test-connection-btn')).toBeInTheDocument())
}

describe('RemotePage — test connection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(remotePointsApi.list).mockResolvedValue([pt1])
    vi.mocked(remoteCertsApi.list).mockResolvedValue([])
    vi.mocked(backupApi.listJobs).mockResolvedValue([])
  })

  it('shows a test button only when editing an existing point', async () => {
    renderPage()
    fireEvent.click(screen.getByText('Remote Points'))
    await waitFor(() => expect(screen.getByTestId('edit-point-backup-101')).toBeInTheDocument())
    expect(screen.queryByTestId('test-connection-btn')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('edit-point-backup-101'))
    await waitFor(() => expect(screen.getByTestId('test-connection-btn')).toBeInTheDocument())
  })

  it('shows a success result and reuses the saved point (no unsaved form fields sent)', async () => {
    vi.mocked(remotePointsApi.test).mockResolvedValue({ ok: true, detail: 'Connexion réussie' })
    await openPointsTabAndEdit()

    fireEvent.click(screen.getByTestId('test-connection-btn'))

    await waitFor(() => expect(screen.getByTestId('test-connection-result')).toBeInTheDocument())
    expect(screen.getByTestId('test-connection-result')).toHaveTextContent('Connexion réussie')
    expect(remotePointsApi.test).toHaveBeenCalledWith('backup-101')
  })

  it('shows a failure detail without throwing', async () => {
    vi.mocked(remotePointsApi.test).mockResolvedValue({
      ok: false,
      detail: 'Authentication failed.',
    })
    await openPointsTabAndEdit()

    fireEvent.click(screen.getByTestId('test-connection-btn'))

    await waitFor(() => expect(screen.getByTestId('test-connection-result')).toBeInTheDocument())
    expect(screen.getByTestId('test-connection-result')).toHaveTextContent('Authentication failed.')
  })
})

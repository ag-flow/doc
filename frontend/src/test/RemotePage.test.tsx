import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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

import { remotePointsApi, remoteCertsApi, backupApi, type RemotePointOut, type BackupJobOut } from '../lib/api'
import { RemotePage, normalizeGitRepo } from '../pages/RemotePage'

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

async function openPointsTab() {
  renderPage()
  fireEvent.click(screen.getByText('Remote Points'))
  await waitFor(() => expect(screen.getByTestId('test-point-backup-101')).toBeInTheDocument())
}

describe('RemotePage — test connection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(remotePointsApi.list).mockResolvedValue([pt1])
    vi.mocked(remoteCertsApi.list).mockResolvedValue([])
    vi.mocked(backupApi.listJobs).mockResolvedValue([])
  })

  it('shows a test button on each point row, and one more in the edit form', async () => {
    await openPointsTab()
    expect(screen.getAllByTestId('test-point-backup-101')).toHaveLength(1)

    fireEvent.click(screen.getByTestId('edit-point-backup-101'))
    await waitFor(() => expect(screen.getAllByTestId('test-point-backup-101')).toHaveLength(2))
  })

  it('shows a success result and reuses the saved point (no unsaved form fields sent)', async () => {
    vi.mocked(remotePointsApi.test).mockResolvedValue({ ok: true, detail: 'Connexion réussie' })
    await openPointsTab()

    fireEvent.click(screen.getByTestId('test-point-backup-101'))

    await waitFor(() => expect(screen.getByTestId('test-connection-result')).toBeInTheDocument())
    expect(screen.getByTestId('test-connection-result')).toHaveTextContent('Connexion réussie')
    expect(remotePointsApi.test).toHaveBeenCalledWith('backup-101')
  })

  it('shows a failure detail without throwing', async () => {
    vi.mocked(remotePointsApi.test).mockResolvedValue({
      ok: false,
      detail: 'Authentication failed.',
    })
    await openPointsTab()

    fireEvent.click(screen.getByTestId('test-point-backup-101'))

    await waitFor(() => expect(screen.getByTestId('test-connection-result')).toBeInTheDocument())
    expect(screen.getByTestId('test-connection-result')).toHaveTextContent('Authentication failed.')
  })
})

describe('RemotePage — génération de clé SSH', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(remotePointsApi.list).mockResolvedValue([])
    vi.mocked(remoteCertsApi.list).mockResolvedValue([])
    vi.mocked(backupApi.listJobs).mockResolvedValue([])
  })
  afterEach(() => vi.unstubAllGlobals())

  async function openCertForm() {
    renderPage()
    fireEvent.click(screen.getByText('Ajouter'))
    await waitFor(() => expect(screen.getByPlaceholderText('Label')).toBeInTheDocument())
  }

  it('disables Générer and explains why outside a secure context (no isSecureContext in jsdom)', async () => {
    await openCertForm()
    const btn = screen.getByRole('button', { name: /Générer/ })
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('title', expect.stringContaining('HTTPS'))
  })

  it('uses the git identity field as the generated key comment when crypto is available', async () => {
    vi.stubGlobal('isSecureContext', true)
    await openCertForm()

    const btn = screen.getByRole('button', { name: /Générer/ })
    await waitFor(() => expect(btn).not.toBeDisabled())

    fireEvent.change(screen.getByTestId('cert-git-identity'), { target: { value: 'deploy@docflow' } })
    fireEvent.click(btn)

    await waitFor(
      () => expect(screen.getByPlaceholderText(/Clé publique/) as HTMLTextAreaElement).not.toHaveValue(''),
      { timeout: 10000 },
    )
    const publicKey = (screen.getByPlaceholderText(/Clé publique/) as HTMLTextAreaElement).value
    expect(publicKey.startsWith('ssh-rsa ')).toBe(true)
    expect(publicKey.endsWith('deploy@docflow')).toBe(true)
  }, 15000)

  it('falls back to the default comment when no identity is given', async () => {
    vi.stubGlobal('isSecureContext', true)
    await openCertForm()

    const btn = screen.getByRole('button', { name: /Générer/ })
    await waitFor(() => expect(btn).not.toBeDisabled())
    fireEvent.click(btn)

    await waitFor(
      () => expect(screen.getByPlaceholderText(/Clé publique/) as HTMLTextAreaElement).not.toHaveValue(''),
      { timeout: 10000 },
    )
    const publicKey = (screen.getByPlaceholderText(/Clé publique/) as HTMLTextAreaElement).value
    expect(publicKey.endsWith('docflow-generated')).toBe(true)
  }, 15000)
})

const gitPoint: RemotePointOut = {
  ...pt1,
  id: 'pt-git',
  slug: 'gh-deploy',
  label: 'GitHub deploy',
  point_type: 'git',
  git_provider: 'github',
  git_repo: 'org/repo',
}

const jobBase: BackupJobOut = {
  id: 'job-1',
  slug: 'job-1',
  label: 'Job 1',
  strategy: 'git_sync',
  enabled: true,
  remote_point_slug: 'gh-deploy',
  workspace_slug: null,
  schedule_cron: null,
  schedule_every_seconds: 3600,
  git_base_path: null,
  created_at: '',
  updated_at: '',
  last_run_at: null,
  last_run_status: null,
}

describe('RemotePage — planification de sauvegarde', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(remotePointsApi.list).mockResolvedValue([gitPoint])
    vi.mocked(remoteCertsApi.list).mockResolvedValue([])
  })

  async function openBackupForm() {
    renderPage()
    fireEvent.click(screen.getByText('Sauvegarde'))
    await waitFor(() => expect(screen.getByText('Nouveau job')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Nouveau job'))
    await waitFor(() => expect(screen.getByTestId('schedule-mode-select')).toBeInTheDocument())
  }

  it('defaults to daily scheduling and sends the matching cron expression', async () => {
    vi.mocked(backupApi.listJobs).mockResolvedValue([])
    vi.mocked(backupApi.createJob).mockResolvedValue(jobBase)
    await openBackupForm()

    expect(screen.getByTestId('schedule-daily-time')).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('schedule-daily-time'), { target: { value: '04:30' } })
    fireEvent.change(screen.getByPlaceholderText('Label'), { target: { value: 'Nightly' } })
    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'gh-deploy' } })
    fireEvent.click(screen.getByText('Créer le job'))

    await waitFor(() => expect(backupApi.createJob).toHaveBeenCalled())
    expect(backupApi.createJob).toHaveBeenCalledWith(
      expect.objectContaining({ schedule_cron: '30 4 * * *', schedule_every_seconds: null }),
    )
  })

  it('sends "0 * * * *" for the hourly preset', async () => {
    vi.mocked(backupApi.listJobs).mockResolvedValue([])
    vi.mocked(backupApi.createJob).mockResolvedValue(jobBase)
    await openBackupForm()

    fireEvent.change(screen.getByTestId('schedule-mode-select'), { target: { value: 'hourly' } })
    fireEvent.change(screen.getByPlaceholderText('Label'), { target: { value: 'Hourly job' } })
    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'gh-deploy' } })
    fireEvent.click(screen.getByText('Créer le job'))

    await waitFor(() => expect(backupApi.createJob).toHaveBeenCalled())
    expect(backupApi.createJob).toHaveBeenCalledWith(
      expect.objectContaining({ schedule_cron: '0 * * * *', schedule_every_seconds: null }),
    )
  })

  it('shows a friendly schedule summary on job cards instead of raw cron', async () => {
    vi.mocked(backupApi.listJobs).mockResolvedValue([
      { ...jobBase, slug: 'daily-job', schedule_cron: '30 4 * * *', schedule_every_seconds: null },
      { ...jobBase, slug: 'hourly-job', schedule_cron: '0 * * * *', schedule_every_seconds: null },
      { ...jobBase, slug: 'interval-job', schedule_cron: null, schedule_every_seconds: 120 },
    ])
    renderPage()
    fireEvent.click(screen.getByText('Sauvegarde'))

    await waitFor(() => expect(screen.getByText(/tous les jours à 04:30/)).toBeInTheDocument())
    expect(screen.getByText(/toutes les heures/)).toBeInTheDocument()
    expect(screen.getByText(/toutes les 120s/)).toBeInTheDocument()
  })
})

describe('normalizeGitRepo', () => {
  it('extrait org/nom depuis une URL https collée telle quelle', () => {
    expect(normalizeGitRepo('https://github.com/ag-flow/backup-docflow.git')).toBe('ag-flow/backup-docflow')
    expect(normalizeGitRepo('https://github.com/ag-flow/backup-docflow')).toBe('ag-flow/backup-docflow')
  })

  it('extrait org/nom depuis une URL SSH', () => {
    expect(normalizeGitRepo('git@github.com:ag-flow/backup-docflow.git')).toBe('ag-flow/backup-docflow')
    expect(normalizeGitRepo('ssh://git@github.com/ag-flow/backup-docflow.git')).toBe('ag-flow/backup-docflow')
  })

  it('laisse org/nom inchangé', () => {
    expect(normalizeGitRepo('ag-flow/backup-docflow')).toBe('ag-flow/backup-docflow')
  })
})

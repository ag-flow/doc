import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
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

import { vaultApi, secretsApi, type VaultSecretOut } from '../lib/api'
import { VaultWalletsTab } from '../pages/VaultWalletsTab'

const key1: VaultSecretOut = {
  id: 'sec-1',
  slug: 'harpocrate-prod',
  label: 'Harpocrate prod',
  secret_type: 'HARPOCRATE_API_KEY',
  storage_type: 'local',
  vault_identifier: null,
  vault_path: null,
  created_at: '',
  updated_at: '',
  used_by_automations: 0,
  used_by_webhooks: 0,
}

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <VaultWalletsTab />
    </QueryClientProvider>,
  )
}

async function openForm() {
  await waitFor(() => expect(screen.getByTestId('vault-add-btn')).toBeInTheDocument())
  fireEvent.click(screen.getByTestId('vault-add-btn'))
}

describe('VaultWalletsTab — bouton Connecter à Harpocrate', () => {
  let assignMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(vaultApi.listWallets).mockResolvedValue([])
    vi.mocked(secretsApi.list).mockResolvedValue([key1])
    assignMock = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { ...window.location, assign: assignMock },
      writable: true,
    })
  })

  it('affiche le bouton, désactivé si alias ou URL vide', async () => {
    renderTab()
    await openForm()

    const btn = screen.getByTestId('vault-connect-btn')
    expect(btn).toBeDisabled()

    fireEvent.change(screen.getByTestId('vault-name-input'), { target: { value: 'mon-coffre' } })
    expect(screen.getByTestId('vault-connect-btn')).toBeDisabled()

    fireEvent.change(screen.getByTestId('vault-name-input'), { target: { value: '' } })
    fireEvent.change(screen.getByTestId('vault-url-input'), { target: { value: 'https://vault.yoops.org' } })
    expect(screen.getByTestId('vault-connect-btn')).toBeDisabled()
  })

  it('au clic avec alias+url remplis, démarre la connexion et redirige en pleine page', async () => {
    vi.mocked(vaultApi.connectStart).mockResolvedValue({ browser_url: 'https://vault.yoops.org/consent/abc' })
    renderTab()
    await openForm()

    fireEvent.change(screen.getByTestId('vault-name-input'), { target: { value: 'mon-coffre' } })
    fireEvent.change(screen.getByTestId('vault-url-input'), { target: { value: 'https://vault.yoops.org' } })
    fireEvent.change(screen.getByTestId('vault-desc-input'), { target: { value: 'desc ici' } })

    const btn = screen.getByTestId('vault-connect-btn')
    expect(btn).not.toBeDisabled()
    fireEvent.click(btn)

    await waitFor(() =>
      expect(vi.mocked(vaultApi.connectStart)).toHaveBeenCalledWith({
        name: 'mon-coffre',
        url: 'https://vault.yoops.org',
        description: 'desc ici',
      }),
    )
    await waitFor(() =>
      expect(assignMock).toHaveBeenCalledWith('https://vault.yoops.org/consent/abc'),
    )
  })

  it('la saisie manuelle (select + créer) reste fonctionnelle', async () => {
    vi.mocked(vaultApi.createWallet).mockResolvedValue({
      id: 'w-1', name: 'mon-coffre', url: 'https://vault.yoops.org', description: null,
      api_key_secret_id: 'sec-1', api_key_secret_label: 'Harpocrate prod',
      used_by: 0, created_at: '', updated_at: '',
    })
    renderTab()
    await openForm()

    fireEvent.change(screen.getByTestId('vault-name-input'), { target: { value: 'mon-coffre' } })
    fireEvent.change(screen.getByTestId('vault-url-input'), { target: { value: 'https://vault.yoops.org' } })
    fireEvent.change(screen.getByTestId('vault-key-select'), { target: { value: 'sec-1' } })

    fireEvent.click(screen.getByTestId('vault-create-btn'))

    await waitFor(() =>
      expect(vi.mocked(vaultApi.createWallet)).toHaveBeenCalledWith({
        name: 'mon-coffre',
        url: 'https://vault.yoops.org',
        description: undefined,
        api_key_secret_id: 'sec-1',
      }),
    )
  })
})

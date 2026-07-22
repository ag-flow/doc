import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    hmacSecretsApi: { list: vi.fn(), create: vi.fn(), reveal: vi.fn(), delete: vi.fn() },
  }
})

import { hmacSecretsApi, type HmacSecretOut } from '../lib/api'
import { HmacSecretsTab } from '../components/HmacSecretsTab'

const s1: HmacSecretOut = { id: 'hs-1', slug: 'wf-prod', label: 'WF prod', created_at: '', updated_at: '' }

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <HmacSecretsTab />
    </QueryClientProvider>,
  )
}

describe('HmacSecretsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
  })

  it('liste les secrets HMAC', async () => {
    vi.mocked(hmacSecretsApi.list).mockResolvedValue([s1])
    renderTab()
    await waitFor(() => expect(screen.getByTestId('hmac-row-wf-prod')).toBeInTheDocument())
    expect(screen.getByText('WF prod')).toBeInTheDocument()
  })

  it('génère un secret (valeur vide) et affiche la bannière de copie', async () => {
    vi.mocked(hmacSecretsApi.list).mockResolvedValue([])
    vi.mocked(hmacSecretsApi.create).mockResolvedValue({ ...s1, value: 'generated-xyz' })
    renderTab()
    await waitFor(() => expect(screen.getByTestId('hmac-add-btn')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('hmac-add-btn'))
    fireEvent.change(screen.getByTestId('hmac-label-input'), { target: { value: 'WF prod' } })
    // Valeur laissée vide → génération serveur
    fireEvent.click(screen.getByTestId('hmac-create-btn'))

    await waitFor(() =>
      expect(vi.mocked(hmacSecretsApi.create)).toHaveBeenCalledWith(
        expect.objectContaining({ label: 'WF prod', slug: 'wf-prod', value: undefined }),
      ),
    )
    await waitFor(() => expect(screen.getByTestId('hmac-created-banner')).toBeInTheDocument())
    expect(screen.getByText('generated-xyz')).toBeInTheDocument()
  })

  it('copie une valeur via révélation', async () => {
    vi.mocked(hmacSecretsApi.list).mockResolvedValue([s1])
    vi.mocked(hmacSecretsApi.reveal).mockResolvedValue({ value: 'revealed-abc' })
    renderTab()
    await waitFor(() => expect(screen.getByTestId('hmac-copy-wf-prod')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('hmac-copy-wf-prod'))
    await waitFor(() => expect(vi.mocked(hmacSecretsApi.reveal)).toHaveBeenCalledWith('hs-1'))
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('revealed-abc'),
    )
  })

  it('supprime après confirmation', async () => {
    vi.mocked(hmacSecretsApi.list).mockResolvedValue([s1])
    vi.mocked(hmacSecretsApi.delete).mockResolvedValue(undefined)
    renderTab()
    await waitFor(() => expect(screen.getByTestId('hmac-delete-wf-prod')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('hmac-delete-wf-prod'))
    await waitFor(() => expect(screen.getByTestId('hmac-delete-confirm-btn')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('hmac-delete-confirm-btn'))
    await waitFor(() => expect(vi.mocked(hmacSecretsApi.delete)).toHaveBeenCalledWith('hs-1'))
  })
})

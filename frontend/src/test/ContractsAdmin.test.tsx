import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    contractsApi: {
      list: vi.fn(),
      import: vi.fn(),
      detail: vi.fn(),
      spec: vi.fn(),
      refresh: vi.fn(),
      delete: vi.fn(),
    },
  }
})

import { contractsApi, type ContractOut } from '../lib/api'
import { ContractsAdmin } from '../pages/ContractsAdmin'
import { ToastProvider } from '../components/Toast'

const CONTRACT: ContractOut = {
  id: 'c1', label: 'RAG', source_url: 'https://rag.example/openapi.json',
  version: '1.2.3', imported_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z',
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider><ContractsAdmin /></ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(contractsApi.list).mockResolvedValue([CONTRACT])
  vi.mocked(contractsApi.detail).mockResolvedValue({
    contract: CONTRACT,
    servers: ['https://rag.example'],
    operations: [
      { operation_id: 'index', method: 'POST', path: '/index', summary: 'Indexer',
        parameters: [], request_body: null, body_skeleton: null, auth_headers: [] },
      { operation_id: 'purge', method: 'DELETE', path: '/purge', summary: 'Purger',
        parameters: [], request_body: null, body_skeleton: null, auth_headers: [] },
      { operation_id: 'health', method: 'GET', path: '/health', summary: null,
        parameters: [], request_body: null, body_skeleton: null, auth_headers: [] },
    ],
  })
})

describe('ContractsAdmin — deux colonnes (Broadsheet)', () => {
  it('le premier contrat est sélectionné d’office et son détail liste les opérations', async () => {
    renderPage()
    const detail = await screen.findByTestId('contract-detail-c1')
    expect(detail).toHaveTextContent('RAG')
    // Le détail (opérations) charge sa propre requête.
    const ops = await screen.findByTestId('contract-operations')
    expect(detail).toHaveTextContent('/index')
    // Verbe en tag : GET neutre, POST cyan, DELETE magenta.
    expect(ops.querySelector('.tag-accent')).toHaveTextContent('POST')
    expect(ops.querySelector('.tag-accent-2')).toHaveTextContent('DELETE')
    expect(ops.querySelector('.tag-neutral')).toHaveTextContent('GET')
  })

  it('un import invalide affiche l’erreur sous le formulaire SANS vider les champs', async () => {
    vi.mocked(contractsApi.import).mockRejectedValue(new Error('spec invalide : paths manquant'))
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /Importer/ }))
    fireEvent.change(screen.getByTestId('contract-label'), { target: { value: 'Mon contrat' } })
    const json = screen.getByTestId('contract-json')
    fireEvent.change(json, { target: { value: '{"openapi": "3.1.0"}' } })
    fireEvent.click(screen.getByTestId('contract-import-submit'))

    const err = await screen.findByTestId('contract-import-error')
    expect(err).toHaveTextContent('paths manquant')
    // Les champs gardent leur contenu : on corrige, on ne retape pas.
    expect(screen.getByTestId('contract-label')).toHaveValue('Mon contrat')
    expect(screen.getByTestId('contract-json')).toHaveValue('{"openapi": "3.1.0"}')
  })

  it('le refresh signale les opérations disparues encore utilisées par un automate', async () => {
    vi.mocked(contractsApi.refresh).mockResolvedValue({
      contract: CONTRACT,
      orphaned_operations: [{ operation_id: 'purge', automations: ['Purge quotidienne'] }],
    })
    renderPage()
    await screen.findByTestId('contract-detail-c1')
    fireEvent.click(screen.getByTestId('contract-refresh-c1'))
    await waitFor(() => expect(contractsApi.refresh).toHaveBeenCalledWith('c1'))
    const toast = await screen.findByTestId('toast')
    expect(toast).toHaveTextContent('purge')
    expect(toast).toHaveTextContent('Purge quotidienne')
  })

  it('suppression via ConfirmDialog (verbe explicite)', async () => {
    vi.mocked(contractsApi.delete).mockResolvedValue(undefined as never)
    renderPage()
    await screen.findByTestId('contract-detail-c1')
    fireEvent.click(screen.getByTestId('contract-delete-c1'))
    fireEvent.click(await screen.findByTestId('contract-delete-dialog-confirm'))
    await waitFor(() => expect(contractsApi.delete).toHaveBeenCalledWith('c1'))
  })
})

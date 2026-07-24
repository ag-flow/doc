import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    contractsApi: { list: vi.fn(), detail: vi.fn() },
    eventsProducerApi: { catalog: vi.fn() },
    secretsApi: { list: vi.fn() },
  }
})

import { contractsApi, eventsProducerApi, secretsApi, type AutomationOut } from '../lib/api'
import { AutomationDialog } from '../components/AutomationDialog'

const contract = { id: 'c1', label: 'RAG', source_url: null, version: '1', imported_at: '', updated_at: '' }

const opBearer = {
  operation_id: 'index', method: 'POST', path: '/index', summary: 'Index',
  parameters: [], request_body: null, body_skeleton: { doc: '' },
  auth_headers: [
    { header: 'Authorization', value_prefix: 'Bearer ', scheme_name: 'BearerApiKey', scheme_type: 'http' },
  ],
}

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <AutomationDialog ws="ws1" initial={null} onSave={vi.fn()} onClose={vi.fn()} saving={false} error={null} />
    </QueryClientProvider>,
  )
}

describe('AutomationDialog — sécurité du contrat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(contractsApi.list).mockResolvedValue([contract])
    vi.mocked(contractsApi.detail).mockResolvedValue({ contract, operations: [opBearer], servers: ['http://rag.example'] })
    vi.mocked(eventsProducerApi.catalog).mockResolvedValue({ revision: 'r', specVersion: '1.0', events: [] })
    vi.mocked(secretsApi.list).mockResolvedValue([
      { id: 's1', slug: 'rag', label: 'RAG key', created_at: '', updated_at: '' },
    ])
  })

  it('ajoute le header d’auth requis (Bearer) à la sélection de l’opération', async () => {
    renderDialog()
    // Attendre que l'option contrat soit rendue, puis la sélectionner.
    await waitFor(() => expect(screen.getByRole('option', { name: 'RAG' })).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('auto-contract-select'), { target: { value: 'c1' } })
    // Attendre que l'opération soit chargée (détail contrat), puis la sélectionner.
    await waitFor(() => expect(screen.getByRole('option', { name: /POST \/index/ })).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('auto-operation-select'), { target: { value: 'index' } })

    // Un header Authorization est auto-ajouté, en mode secret, préfixe « Bearer ».
    await waitFor(() =>
      expect((screen.getByTestId('header-name-0') as HTMLInputElement).value).toBe('Authorization'),
    )
    const secretSelect = screen.getByTestId('header-secret-0') as HTMLSelectElement
    // La liste de sélection propose « Mes secrets ».
    expect(screen.getByRole('option', { name: 'RAG key' })).toBeInTheDocument()
    // Sélectionner le secret pose la référence ${secret://id}.
    fireEvent.change(secretSelect, { target: { value: '${secret://s1}' } })
    expect(secretSelect.value).toBe('${secret://s1}')
  })

  it('construit l’URL d’appel (server + path) à la sélection de l’opération', async () => {
    renderDialog()
    await waitFor(() => expect(screen.getByRole('option', { name: 'RAG' })).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('auto-contract-select'), { target: { value: 'c1' } })
    await waitFor(() => expect(screen.getByRole('option', { name: /POST \/index/ })).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('auto-operation-select'), { target: { value: 'index' } })
    await waitFor(() =>
      expect((screen.getByTestId('auto-url') as HTMLInputElement).value).toBe('http://rag.example/index'),
    )
  })

  it('ajoute le header d’auth à l’OUVERTURE d’un automate existant (sans changer d’opération)', async () => {
    const initial: AutomationOut = {
      id: 'a1', workspace_technical_key: 'wk', label: 'Rag', active: false, pending_count: 0,
      event_codes: ['docflow.document.updated.v1'], on_create: false, on_update: false,
      delay_minutes: 0, contract_ref: 'c1', operation_id: 'index',
      url: 'https://rag.example/api', http_method: 'POST', body_template: '{}',
      headers: [], created_at: '', updated_at: '',
    }
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <AutomationDialog ws="ws1" initial={initial} onSave={vi.fn()} onClose={vi.fn()} saving={false} error={null} />
      </QueryClientProvider>,
    )
    // Le header requis apparaît dès le chargement du contrat, sans interaction.
    await waitFor(() =>
      expect((screen.getByTestId('header-name-0') as HTMLInputElement).value).toBe('Authorization'),
    )
  })
})

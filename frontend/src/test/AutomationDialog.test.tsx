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
    docsApi: { getBlocks: vi.fn() },
    api: { get: vi.fn() },
  }
})

import { contractsApi, eventsProducerApi, secretsApi, docsApi, api, type AutomationOut } from '../lib/api'
import { AutomationDialog } from '../components/AutomationDialog'

const contract = { id: 'c1', label: 'RAG', source_url: null, version: '1', imported_at: '', updated_at: '' }

const opBearer = {
  operation_id: 'index', method: 'POST', path: '/index', summary: 'Index',
  parameters: [], request_body: null, body_skeleton: { doc: '' },
  auth_headers: [
    { header: 'Authorization', value_prefix: 'Bearer ', scheme_name: 'BearerApiKey', scheme_type: 'http' },
  ],
}

function renderDialog(initial: AutomationOut | null = null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <AutomationDialog ws="ws1" initial={initial} onSave={vi.fn()} onClose={vi.fn()} saving={false} error={null} />
    </QueryClientProvider>,
  )
}

// Le dialogue démarre sur l'onglet Libellé ; le contrat/opération sont sur « Appel ».
function openCallTab() {
  fireEvent.click(screen.getByTestId('auto-tab-call'))
}

describe('AutomationDialog — onglets & sécurité du contrat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(contractsApi.list).mockResolvedValue([contract])
    vi.mocked(contractsApi.detail).mockResolvedValue({ contract, operations: [opBearer], servers: ['http://rag.example'] })
    vi.mocked(eventsProducerApi.catalog).mockResolvedValue({ revision: 'r', specVersion: '1.0', events: [] })
    vi.mocked(secretsApi.list).mockResolvedValue([
      { id: 's1', slug: 'rag', label: 'RAG key', created_at: '', updated_at: '', used_by_automations: 0, used_by_webhooks: 0 },
    ])
    vi.mocked(docsApi.getBlocks).mockResolvedValue([])
    vi.mocked(api.get).mockResolvedValue([])
  })

  it('ajoute le header d’auth requis (Bearer) à la sélection de l’opération', async () => {
    renderDialog()
    openCallTab()
    await waitFor(() => expect(screen.getByRole('option', { name: 'RAG' })).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('auto-contract-select'), { target: { value: 'c1' } })
    await waitFor(() => expect(screen.getByRole('option', { name: /POST \/index/ })).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('auto-operation-select'), { target: { value: 'index' } })

    await waitFor(() =>
      expect((screen.getByTestId('header-name-0') as HTMLInputElement).value).toBe('Authorization'),
    )
    const secretSelect = screen.getByTestId('header-secret-0') as HTMLSelectElement
    expect(screen.getByRole('option', { name: 'RAG key' })).toBeInTheDocument()
    fireEvent.change(secretSelect, { target: { value: '${secret://s1}' } })
    expect(secretSelect.value).toBe('${secret://s1}')
  })

  it('construit l’URL d’appel (server + path) à la sélection de l’opération', async () => {
    renderDialog()
    openCallTab()
    await waitFor(() => expect(screen.getByRole('option', { name: 'RAG' })).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('auto-contract-select'), { target: { value: 'c1' } })
    await waitFor(() => expect(screen.getByRole('option', { name: /POST \/index/ })).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('auto-operation-select'), { target: { value: 'index' } })
    await waitFor(() =>
      expect((screen.getByTestId('auto-url') as HTMLInputElement).value).toBe('http://rag.example/index'),
    )
  })

  it('préserve body_template quand on enregistre SANS visiter l’onglet Appel', async () => {
    const initial: AutomationOut = {
      id: 'a1', workspace_technical_key: 'wk', label: 'Rag', active: false, pending_count: 0,
      event_codes: ['docflow.document.updated.v1'], workspace_slugs: ['ws1'], position: 1, stop_chain: false,
      block_slugs: [], functional_type_slugs: [],
      on_create: false, on_update: false, delay_minutes: 0, contract_ref: null, operation_id: null,
      url: 'https://rag.example/api', http_method: 'POST', body_template: '{"doc": "{title}"}',
      headers: [], created_at: '', updated_at: '',
    }
    const onSave = vi.fn()
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <AutomationDialog ws="ws1" initial={initial} onSave={onSave} onClose={vi.fn()} saving={false} error={null} />
      </QueryClientProvider>,
    )
    // On reste sur l'onglet Libellé (l'éditeur JSON n'est jamais monté) et on enregistre.
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0][0].body_template).toBe('{"doc": "{title}"}')
  })

  it('ajoute le header d’auth à l’OUVERTURE d’un automate existant', async () => {
    const initial: AutomationOut = {
      id: 'a1', workspace_technical_key: 'wk', label: 'Rag', active: false, pending_count: 0,
      event_codes: ['docflow.document.updated.v1'], workspace_slugs: ['ws1'], position: 1, stop_chain: false,
      block_slugs: [], functional_type_slugs: [],
      on_create: false, on_update: false, delay_minutes: 0, contract_ref: 'c1', operation_id: 'index',
      url: 'https://rag.example/api', http_method: 'POST', body_template: '{}',
      headers: [], created_at: '', updated_at: '',
    }
    renderDialog(initial)
    openCallTab()
    await waitFor(() =>
      expect((screen.getByTestId('header-name-0') as HTMLInputElement).value).toBe('Authorization'),
    )
  })
})

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

function renderDialog(initial: AutomationOut | null, onSave = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <AutomationDialog ws="ws1" initial={initial} onSave={onSave} onClose={vi.fn()} saving={false} error={null} />
    </QueryClientProvider>,
  )
  return onSave
}

/** Un automate existant, sans pré-condition : le cas de tous ceux déjà en base. */
const base = {
  id: 'a1', workspace_technical_key: null, label: 'Créer le workspace RAG',
  active: true, pending_count: 0, position: 1, workspace_slugs: [],
  event_codes: ['docflow.block.created.v1'], block_slugs: [], block_templates: [],
  stop_chain: false, functional_type_slugs: [], on_create: false, on_update: false,
  delay_minutes: 0, contract_ref: null, operation_id: null,
  url: 'https://rag.example/api/v1/workspaces', http_method: 'POST',
  body_template: '{"name":"x"}', precheck: null, headers: [],
  created_at: '', updated_at: '',
} as unknown as AutomationOut

beforeEach(() => {
  vi.mocked(contractsApi.list).mockResolvedValue([])
  vi.mocked(eventsProducerApi.catalog).mockResolvedValue({ revision: 'r', specVersion: '1.0', events: [] })
  vi.mocked(secretsApi.list).mockResolvedValue([])
  vi.mocked(docsApi.getBlocks).mockResolvedValue([])
  vi.mocked(api.get).mockResolvedValue([])
})

describe('AutomationDialog — pré-condition', () => {
  it('n’envoie aucune pré-condition tant que la case n’est pas cochée', async () => {
    const onSave = renderDialog(base)

    fireEvent.click(await screen.findByTestId('auto-tab-call'))
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0]![0].precheck).toBeNull()
  })

  it('construit la pré-condition « ne pas recréer ce qui existe »', async () => {
    const onSave = renderDialog(base)

    fireEvent.click(await screen.findByTestId('auto-tab-call'))
    fireEvent.click(screen.getByTestId('auto-precheck-enable'))
    fireEvent.change(screen.getByTestId('auto-precheck-url'), {
      target: { value: 'https://rag.example/api/v1/workspaces/{event.workspaceSlug}-docs' },
    })
    fireEvent.change(screen.getByTestId('auto-precheck-rule-status-0'), { target: { value: '404' } })
    fireEvent.change(screen.getByTestId('auto-precheck-rule-then-0'), { target: { value: 'proceed' } })
    fireEvent.change(screen.getByTestId('auto-precheck-default'), { target: { value: 'skip' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0]![0].precheck).toEqual({
      url: 'https://rag.example/api/v1/workspaces/{event.workspaceSlug}-docs',
      method: 'GET',
      rules: [{ status: [404], then: 'proceed' }],
      default: 'skip',
    })
  })

  it('relit une pré-condition existante au lieu de la perdre', async () => {
    /** Ouvrir puis enregistrer sans toucher à la section ne doit rien effacer —
     *  c'est le défaut qui a déjà coûté un body_template. */
    const withPrecheck = {
      ...base,
      precheck: {
        url: 'https://rag.example/check', method: 'GET',
        rules: [{ status: [200], then: 'proceed' }], default: 'defer',
      },
    } as unknown as AutomationOut
    const onSave = renderDialog(withPrecheck)

    fireEvent.click(await screen.findByTestId('auto-tab-call'))
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0]![0].precheck).toEqual({
      url: 'https://rag.example/check', method: 'GET',
      rules: [{ status: [200], then: 'proceed' }], default: 'defer',
    })
  })

  it('décocher la case retire la pré-condition', async () => {
    const withPrecheck = {
      ...base,
      precheck: { url: 'https://rag.example/check', method: 'GET', rules: [], default: 'skip' },
    } as unknown as AutomationOut
    const onSave = renderDialog(withPrecheck)

    fireEvent.click(await screen.findByTestId('auto-tab-call'))
    fireEvent.click(screen.getByTestId('auto-precheck-enable'))
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0]![0].precheck).toBeNull()
  })

  it('n’envoie pas de critère de statut vide', async () => {
    /** Un `status: []` stocké se relirait comme un critère POSÉ que rien ne
     *  satisfait — la règle ne matcherait jamais, en silence. */
    const onSave = renderDialog(base)

    fireEvent.click(await screen.findByTestId('auto-tab-call'))
    fireEvent.click(screen.getByTestId('auto-precheck-enable'))
    fireEvent.change(screen.getByTestId('auto-precheck-url'), {
      target: { value: 'https://rag.example/check' },
    })
    // La règle proposée par défaut porte un statut : on le vide pour n'avoir
    // qu'un critère de corps, qui est le cas qu'on veut éprouver.
    fireEvent.change(screen.getByTestId('auto-precheck-rule-status-0'), { target: { value: '' } })
    fireEvent.change(screen.getByTestId('auto-precheck-rule-path-0'), { target: { value: 'state' } })
    fireEvent.change(screen.getByTestId('auto-precheck-rule-equals-0'), { target: { value: 'ready' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(onSave).toHaveBeenCalled())
    const rule = onSave.mock.calls[0]![0].precheck.rules[0]
    expect(rule.status).toBeUndefined()
    expect(rule).toMatchObject({ path: 'state', equals: 'ready' })
  })
})

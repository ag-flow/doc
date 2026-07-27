import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    eventsProducerApi: {
      get: vi.fn(),
      update: vi.fn(),
      testConnection: vi.fn(),
      catalog: vi.fn(),
    },
    hmacSecretsApi: { list: vi.fn(), create: vi.fn(), reveal: vi.fn(), delete: vi.fn() },
    getToken: vi.fn(() => 'tok'),
  }
})

import {
  eventsProducerApi,
  hmacSecretsApi,
  type EventsProducerConfigOut,
  type EventCatalog,
  type HmacSecretOut,
} from '../lib/api'
import { EventsProducerAdmin } from '../pages/EventsProducerAdmin'

const catalog: EventCatalog = {
  revision: 'rev1',
  specVersion: '1.0',
  events: [
    { eventCode: 'docflow.document.created.v1', latestVersion: 1, title: 'Document créé', description: '', deprecated: false },
    { eventCode: 'docflow.document.updated.v1', latestVersion: 1, title: 'Document mis à jour', description: '', deprecated: false },
  ],
}

const cfg: EventsProducerConfigOut = {
  enabled: false,
  ingestion_url: 'https://workflow.example/ing',
  source_id: 'docflow-prod',
  source_uri: 'docflow',
  allowed_events: ['docflow.document.created.v1'],
  secret_configured: true,
}

const hmacSecrets: HmacSecretOut[] = [
  { id: 'hs-1', slug: 'wf-prod', label: 'WF prod', created_at: '', updated_at: '' },
]

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/admin/events-producer']}>
        <EventsProducerAdmin />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('EventsProducerAdmin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(hmacSecretsApi.list).mockResolvedValue(hmacSecrets)
    vi.mocked(eventsProducerApi.catalog).mockResolvedValue(catalog)
  })

  it('charge la config et pré-remplit le formulaire', async () => {
    vi.mocked(eventsProducerApi.get).mockResolvedValue(cfg)
    renderPage()
    await waitFor(() =>
      expect((screen.getByTestId('ep-ingestion-url') as HTMLInputElement).value).toBe('https://workflow.example/ing'),
    )
    // Catalogue rendu, event pré-coché depuis la liste blanche
    await waitFor(() =>
      expect(screen.getByTestId('ep-event-docflow.document.created.v1')).toBeChecked(),
    )
    expect(screen.getByTestId('ep-event-docflow.document.updated.v1')).not.toBeChecked()
  })

  it('enregistre la config avec le corps attendu (secret non renvoyé si vide)', async () => {
    vi.mocked(eventsProducerApi.get).mockResolvedValue(cfg)
    vi.mocked(eventsProducerApi.update).mockResolvedValue(cfg)
    renderPage()
    await waitFor(() => expect(screen.getByTestId('ep-save-btn')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('ep-event-docflow.document.updated.v1'))
    fireEvent.click(screen.getByTestId('ep-save-btn'))

    await waitFor(() =>
      expect(vi.mocked(eventsProducerApi.update)).toHaveBeenCalledWith(
        expect.objectContaining({
          ingestion_url: 'https://workflow.example/ing',
          allowed_events: ['docflow.document.created.v1', 'docflow.document.updated.v1'],
        }),
      ),
    )
    // Secret laissé vide → pas de secret_ref dans le corps (on ne réécrit pas l'existant)
    const body = vi.mocked(eventsProducerApi.update).mock.calls[0][0]
    expect(body).not.toHaveProperty('secret_ref')
  })

  it('sélectionner un secret HMAC envoie une référence ${hmac://id}', async () => {
    vi.mocked(eventsProducerApi.get).mockResolvedValue({ ...cfg, secret_configured: false })
    vi.mocked(eventsProducerApi.update).mockResolvedValue(cfg)
    renderPage()
    await waitFor(() => expect(screen.getByTestId('ep-secret-select')).toBeInTheDocument())

    fireEvent.change(screen.getByTestId('ep-secret-select'), { target: { value: 'hs-1' } })
    fireEvent.click(screen.getByTestId('ep-save-btn'))

    await waitFor(() =>
      expect(vi.mocked(eventsProducerApi.update)).toHaveBeenCalledWith(
        expect.objectContaining({ secret_ref: '${hmac://hs-1}' }),
      ),
    )
  })

  it('affiche le résultat du test de connexion', async () => {
    vi.mocked(eventsProducerApi.get).mockResolvedValue(cfg)
    vi.mocked(eventsProducerApi.testConnection).mockResolvedValue({ status: 202, ok: true })
    renderPage()
    await waitFor(() => expect(screen.getByTestId('ep-test-btn')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('ep-test-btn'))
    await waitFor(() => expect(screen.getByTestId('ep-test-result')).toBeInTheDocument())
    expect(screen.getByTestId('ep-test-result').textContent).toContain('202')
  })

  it('désactive le test quand la config est incomplète (pas de secret)', async () => {
    vi.mocked(eventsProducerApi.get).mockResolvedValue({ ...cfg, secret_configured: false })
    renderPage()
    await waitFor(() => expect(screen.getByTestId('ep-test-btn')).toBeInTheDocument())
    expect(screen.getByTestId('ep-test-btn')).toBeDisabled()
  })
})

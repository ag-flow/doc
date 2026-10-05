import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    webhooksApi: {
      list: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      test: vi.fn(),
    },
    getToken: vi.fn(() => 'tok'),
  }
})

import { webhooksApi, type WebhookOut } from '../lib/api'
import { WebhooksAdmin } from '../pages/WebhooksAdmin'

const wh1: WebhookOut = {
  id: 'wh-1',
  workspace_technical_key: 'wk-1',
  label: 'Mon hook',
  url: 'https://example.com/{id_document}',
  headers: { 'X-Token': 'secret' },
  events: ['document.created'],
  active: true,
  created_at: '',
  updated_at: '',
  last_delivery_at: null,
  last_delivery_status: null,
  last_delivery_error: null,
  failures_24h: 0,
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/ws/devpod-ui/webhooks']}>
        <Routes>
          <Route path="/ws/:wsSlug/webhooks" element={<WebhooksAdmin />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('WebhooksAdmin', () => {
  beforeEach(() => vi.clearAllMocks())

  // DoD 29 — liste vide
  it('shows empty state when no webhooks', async () => {
    vi.mocked(webhooksApi.list).mockResolvedValue([])
    renderPage()
    await waitFor(() => expect(screen.getByTestId('wh-empty')).toBeInTheDocument())
  })

  // DoD 29 — liste avec un webhook
  it('renders webhook list', async () => {
    vi.mocked(webhooksApi.list).mockResolvedValue([wh1])
    renderPage()
    await waitFor(() => expect(screen.getByTestId(`webhook-row-${wh1.id}`)).toBeInTheDocument())
    expect(screen.getByText('Mon hook')).toBeInTheDocument()
    expect(screen.getByTestId(`wh-status-${wh1.id}`).textContent).toBe('Actif')
  })

  // DoD 29 — formulaire de création
  it('opens create form and submits', async () => {
    vi.mocked(webhooksApi.list).mockResolvedValue([])
    vi.mocked(webhooksApi.create).mockResolvedValue(wh1)
    renderPage()
    await waitFor(() => expect(screen.getByTestId('create-webhook-btn')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('create-webhook-btn'))
    expect(screen.getByTestId('webhook-form')).toBeInTheDocument()

    fireEvent.change(screen.getByTestId('wh-label'), { target: { value: 'Mon hook' } })
    fireEvent.change(screen.getByTestId('wh-url'), { target: { value: 'https://example.com/' } })
    fireEvent.click(screen.getByTestId('event-document.created'))

    fireEvent.click(screen.getByTestId('wh-submit'))
    await waitFor(() => expect(vi.mocked(webhooksApi.create)).toHaveBeenCalledWith(
      'devpod-ui',
      expect.objectContaining({
        label: 'Mon hook',
        url: 'https://example.com/',
        events: ['document.created'],
      }),
    ))
  })

  // DoD 29 — headers clé-valeur
  it('allows adding and removing header rows', async () => {
    vi.mocked(webhooksApi.list).mockResolvedValue([])
    renderPage()
    await waitFor(() => expect(screen.getByTestId('create-webhook-btn')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('create-webhook-btn'))
    fireEvent.click(screen.getByTestId('add-header-btn'))

    expect(screen.getByTestId('header-row-0')).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('header-key-0'), { target: { value: 'X-Token' } })
    fireEvent.change(screen.getByTestId('header-value-0'), { target: { value: 'secret' } })

    fireEvent.click(screen.getByTestId('remove-header-0'))
    expect(screen.queryByTestId('header-row-0')).not.toBeInTheDocument()
  })

  // DoD 29 — action Test
  it('shows test result after clicking test button', async () => {
    vi.mocked(webhooksApi.list).mockResolvedValue([wh1])
    vi.mocked(webhooksApi.test).mockResolvedValue({ status_code: 200, error: null, duration_ms: 123 })
    renderPage()
    await waitFor(() => expect(screen.getByTestId(`test-webhook-${wh1.id}`)).toBeInTheDocument())

    fireEvent.click(screen.getByTestId(`test-webhook-${wh1.id}`))
    await waitFor(() =>
      expect(screen.getByTestId(`test-result-${wh1.id}`)).toBeInTheDocument(),
    )
    expect(screen.getByTestId(`test-result-${wh1.id}`).textContent).toContain('HTTP 200')
  })

  // DoD 29 — bouton supprimer
  it('calls delete on webhook delete button', async () => {
    vi.mocked(webhooksApi.list).mockResolvedValue([wh1])
    vi.mocked(webhooksApi.delete).mockResolvedValue(undefined)
    renderPage()
    await waitFor(() => expect(screen.getByTestId(`delete-webhook-${wh1.id}`)).toBeInTheDocument())

    fireEvent.click(screen.getByTestId(`delete-webhook-${wh1.id}`))
    // La suppression passe désormais par une confirmation à verbe explicite.
    fireEvent.click(await screen.findByTestId('wh-delete-dialog-confirm'))
    await waitFor(() =>
      expect(vi.mocked(webhooksApi.delete)).toHaveBeenCalledWith('devpod-ui', wh1.id),
    )
  })
})

describe('journal de livraison (écart n°1)', () => {
  it('dernier envoi en cyan/magenta selon le code, échecs 24 h en magenta si non nuls', async () => {
    vi.mocked(webhooksApi.list).mockResolvedValue([
      { ...wh1, last_delivery_at: '2026-07-27T10:00:00Z', last_delivery_status: 500,
        last_delivery_error: 'boom', failures_24h: 3 },
    ])
    renderPage()
    const delivery = await screen.findByTestId(`delivery-cell-${wh1.id}`)
    expect(delivery).toHaveTextContent('HTTP 500')
    expect(delivery.querySelector('.text-accent-2-700')).not.toBeNull()
    const failures = screen.getByTestId(`failures-cell-${wh1.id}`)
    expect(failures.querySelector('.tag-accent-2')).toHaveTextContent('3')
  })

  it('aucune livraison → tirets neutres, pas de fausse alerte', async () => {
    vi.mocked(webhooksApi.list).mockResolvedValue([wh1])
    renderPage()
    const delivery = await screen.findByTestId(`delivery-cell-${wh1.id}`)
    expect(delivery).toHaveTextContent('—')
    expect(screen.getByTestId(`failures-cell-${wh1.id}`)).toHaveTextContent('0')
  })
})

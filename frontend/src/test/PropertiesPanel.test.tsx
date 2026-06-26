import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    api: { ...actual.api, get: vi.fn() },
    docsApi: {
      ...actual.docsApi,
      getDocumentValues: vi.fn(),
      putDocumentValue: vi.fn(),
    },
  }
})

import { api, docsApi, type PropertyValueOut } from '../lib/api'
import { PropertiesPanel } from '../components/PropertiesPanel'

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <PropertiesPanel ws="ws" docId="d1" />
    </QueryClientProvider>,
  )
}

describe('PropertiesPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders fields for each property', async () => {
    const values: PropertyValueOut[] = [
      {
        prop_slug: 'title2',
        prop_label: 'Sous-titre',
        type: 'text',
        version: 1,
        value: 'Bonjour',
        allowed_value_slug: null,
        allowed_value_label: null,
        required: false,
      },
      {
        prop_slug: 'status',
        prop_label: 'Statut',
        type: 'restricted_list',
        version: 1,
        value: null,
        allowed_value_slug: 'todo',
        allowed_value_label: 'À faire',
        required: true,
      },
    ]
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue(values)
    vi.mocked(api.get).mockResolvedValue([
      {
        slug: 'epic',
        label: 'Epic',
        properties: [
          {
            slug: 'status',
            label: 'Statut',
            type: 'restricted_list',
            required: true,
            allowed_values: [{ slug: 'todo', label: 'À faire', color: null, position: 0 }],
          },
        ],
      },
    ])

    renderPanel()
    await waitFor(() => expect(screen.getByTestId('property-title2')).toBeInTheDocument())
    expect(screen.getByTestId('property-status')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Bonjour')).toBeInTheDocument()
  })

  it('shows empty message when no properties', async () => {
    vi.mocked(docsApi.getDocumentValues).mockResolvedValue([])
    vi.mocked(api.get).mockResolvedValue([])
    renderPanel()
    await waitFor(() => expect(screen.getByText('Aucune propriété')).toBeInTheDocument())
  })
})

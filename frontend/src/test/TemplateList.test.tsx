import { render, screen, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import '../lib/i18n'
import TemplateList from '../pages/TemplateList'
import { api } from '../lib/api'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  }
})

const mockTemplates = [
  {
    template: 'agile-basic',
    label: 'Projet agile (epic / feature / story / atdd)',
    version: 1,
    path: 'agile-basic.yaml',
    concrete_types: 4,
    type_slugs: ['epic', 'feature', 'story', 'atdd'],
  },
]

function wrapper(children: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => vi.clearAllMocks())

describe('TemplateList', () => {
  it('affiche les cartes de templates', async () => {
    vi.mocked(api.get).mockResolvedValue(mockTemplates)
    render(wrapper(<TemplateList />))
    await waitFor(() =>
      expect(screen.getByTestId('tpl-card-agile-basic')).toBeInTheDocument()
    )
    expect(screen.getByText('agile-basic')).toBeInTheDocument()
    expect(screen.getByText('v1')).toBeInTheDocument()
    expect(screen.getByText('epic')).toBeInTheDocument()
    expect(screen.getByText('story')).toBeInTheDocument()
    expect(screen.getByTestId('import-btn-agile-basic')).toBeDisabled()
  })

  it("affiche l'état vide si aucun template", async () => {
    vi.mocked(api.get).mockResolvedValue([])
    render(wrapper(<TemplateList />))
    await waitFor(() =>
      expect(screen.getByTestId('empty')).toBeInTheDocument()
    )
    expect(screen.getByText(/Aucun template/i)).toBeInTheDocument()
  })

  it("affiche l'erreur si la requête échoue", async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('Network error'))
    render(wrapper(<TemplateList />))
    await waitFor(() =>
      expect(screen.getByTestId('error')).toBeInTheDocument()
    )
  })
})

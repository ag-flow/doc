import { render, screen, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import '../lib/i18n'
import TemplateList, { normalizeSourceUrl } from '../pages/TemplateList'
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

describe('normalizeSourceUrl', () => {
  it('convertit une URL github blob vers son équivalent raw', () => {
    expect(
      normalizeSourceUrl('https://github.com/ag-flow/ressources/blob/main/Docflow/templates/toc.txt'),
    ).toBe('https://raw.githubusercontent.com/ag-flow/ressources/refs/heads/main/Docflow/templates')
  })

  it('convertit une URL github tree vers son équivalent raw', () => {
    expect(
      normalizeSourceUrl('https://github.com/ag-flow/ressources/tree/main/Docflow/templates/'),
    ).toBe('https://raw.githubusercontent.com/ag-flow/ressources/refs/heads/main/Docflow/templates')
  })

  it('strippe toc.txt et le slash final sans toucher au reste', () => {
    expect(normalizeSourceUrl('https://templates.example.com/base/toc.txt')).toBe(
      'https://templates.example.com/base',
    )
    expect(normalizeSourceUrl('https://templates.example.com/base/')).toBe(
      'https://templates.example.com/base',
    )
  })

  it('laisse une URL raw déjà correcte inchangée', () => {
    const raw = 'https://raw.githubusercontent.com/ag-flow/ressources/refs/heads/main/Docflow/templates'
    expect(normalizeSourceUrl(raw)).toBe(raw)
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  getToken: vi.fn(() => 'tok'),
  setToken: vi.fn(),
  clearToken: vi.fn(),
}))

import { api } from '../lib/api'
import { TypesAdmin, flattenTypeTree, groupTypeTree } from '../pages/TypesAdmin'
import type { FunctionalTypeRich } from '../lib/api'

function renderWithProviders(ws = 'my-ws') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/ws/${ws}/types`]}>
        <Routes>
          <Route path="/ws/:wsSlug/types" element={<TypesAdmin />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TypesAdmin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders types from API', async () => {
    vi.mocked(api.get).mockResolvedValue([
      { slug: 'epic', label: 'Epic', parent_slug: null, id: '1' },
    ])
    renderWithProviders()
    await waitFor(() => expect(screen.getByTestId('types-table')).toBeInTheDocument())
    expect(screen.getByText('epic')).toBeInTheDocument()
    expect(screen.getByText('Epic')).toBeInTheDocument()
  })

  it('shows create button after load', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderWithProviders()
    await waitFor(() => expect(screen.getByTestId('create-type-btn')).toBeInTheDocument())
  })

  it('shows the template slug alongside its label in the import dropdown', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/templates') {
        return Promise.resolve([
          { template: 'agile-project', label: 'Projet agile', version: 2, path: '', concrete_types: 0, type_slugs: [] },
        ])
      }
      return Promise.resolve([])
    })
    renderWithProviders()
    await waitFor(() => expect(screen.getByTestId('import-template-btn')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('import-template-btn'))
    await waitFor(() =>
      expect(screen.getByText('Projet agile (v2) — agile-project')).toBeInTheDocument(),
    )
  })
})

describe('flattenTypeTree', () => {
  const mk = (slug: string, label: string, parent: string | null) =>
    ({
      id: slug,
      slug,
      label,
      parent_slug: parent,
      workspace_slug: 'ws',
      content_template: null,
      created_at: '',
      updated_at: '',
      properties: [],
    }) as FunctionalTypeRich

  it('ordonne racines puis enfants, avec profondeur', () => {
    const flat = flattenTypeTree([
      mk('story', 'User Story', 'feature'),
      mk('epic', 'Epic', null),
      mk('feature', 'Feature', 'epic'),
      mk('section', 'Section', null),
    ])
    expect(flat.map((n) => n.type.slug)).toEqual(['epic', 'feature', 'story', 'section'])
    expect(flat.map((n) => n.depth)).toEqual([0, 1, 2, 0])
  })

  it('traite un parent inconnu comme racine', () => {
    const flat = flattenTypeTree([mk('orphelin', 'Orphelin', 'disparu')])
    expect(flat).toHaveLength(1)
    expect(flat[0].depth).toBe(0)
  })

  it('ne boucle pas sur un cycle de parenté', () => {
    const flat = flattenTypeTree([mk('a', 'A', 'b'), mk('b', 'B', 'a')])
    expect(flat).toHaveLength(2)
  })
})

describe('groupTypeTree', () => {
  const mk = (slug: string, label: string, parent: string | null, tpl: string | null) =>
    ({
      id: slug,
      slug,
      label,
      parent_slug: parent,
      workspace_slug: 'ws',
      content_template: null,
      source_template: tpl,
      created_at: '',
      updated_at: '',
      properties: [],
    }) as FunctionalTypeRich

  it('regroupe par template de la racine, manuels en dernier', () => {
    const groups = groupTypeTree([
      mk('manuel', 'Manuel', null, null),
      mk('epic', 'Epic', null, 'agile-basic'),
      mk('feature', 'Feature', 'epic', 'agile-basic'),
      mk('section', 'Section', null, 'doc-basic'),
    ])
    expect(groups.map((g) => g.template)).toEqual(['agile-basic', 'doc-basic', null])
    expect(groups[0].nodes.map((n) => n.type.slug)).toEqual(['epic', 'feature'])
    expect(groups[2].nodes.map((n) => n.type.slug)).toEqual(['manuel'])
  })

  it("un descendant suit sa racine même si sa provenance diffère", () => {
    const groups = groupTypeTree([
      mk('epic', 'Epic', null, 'agile-basic'),
      mk('custom', 'Custom', 'epic', null),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].nodes.map((n) => n.type.slug)).toEqual(['epic', 'custom'])
  })
})

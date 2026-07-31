import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
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
      source_template: null,
      created_at: '',
      updated_at: '',
      documents_count: 0,
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
      documents_count: 0,
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

// ── Écran Types Broadsheet : édition en place, DoD ──────────────────────────

const RICH_TYPE = {
  id: 't1', slug: 'epic', label: 'Epic', parent_slug: null, workspace_slug: 'ws',
  content_template: null, source_template: null, created_at: '', updated_at: '',
  documents_count: 5,
  properties: [
    {
      slug: 'statut', label: 'Statut', type: 'restricted_list', required: false,
      behavior: null, default_value: null,
      allowed_values: [{ slug: 'fait', label: 'Fait', color: null, position: 0 }],
    },
    {
      slug: 'url-confluence', label: 'url confluence', type: 'url', required: false,
      behavior: null, default_value: null, allowed_values: [],
    },
  ],
}

describe('TypesAdmin — édition en place (Broadsheet)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.get).mockResolvedValue([RICH_TYPE])
  })

  it('la ligne porte le résumé des propriétés et le nombre de documents', async () => {
    renderWithProviders()
    expect(await screen.findByTestId('props-summary-epic')).toHaveTextContent('Statut')
    expect(screen.getByTestId('docs-count-epic')).toHaveTextContent('5 docs')
  })

  it('le panneau liste AUSSI les propriétés scalaires (url, text…) et permet leur suppression', async () => {
    renderWithProviders()
    fireEvent.click(await screen.findByTestId('type-row-epic'))
    // La propriété scalaire est visible : libellé, slug, type.
    const row = await screen.findByTestId('prop-row-url-confluence')
    expect(row).toHaveTextContent('url confluence')
    expect(row).toHaveTextContent('url')
    // Suppression : dialogue de confirmation puis DELETE confirm=true.
    vi.mocked(api.delete).mockResolvedValue(undefined as never)
    fireEvent.click(screen.getByTestId('delete-prop-url-confluence'))
    expect(await screen.findByTestId('delete-prop-dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('delete-prop-dialog-confirm'))
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith(
        '/workspaces/my-ws/types/epic/properties/url-confluence?confirm=true',
      ),
    )
  })

  it('édition d’une propriété : slug figé, libellé + type envoyés en PATCH', async () => {
    renderWithProviders()
    fireEvent.click(await screen.findByTestId('type-row-epic'))
    fireEvent.click(await screen.findByTestId('edit-prop-url-confluence'))
    // Le slug est affiché mais IMMUABLE.
    expect(screen.getByTestId('edit-prop-slug')).toBeDisabled()
    fireEvent.change(screen.getByTestId('edit-prop-label'), { target: { value: 'URL Confluence' } })
    fireEvent.change(screen.getByTestId('edit-prop-type'), { target: { value: 'text' } })
    vi.mocked(api.patch).mockResolvedValue(undefined as never)
    fireEvent.click(screen.getByTestId('edit-prop-save'))
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        '/workspaces/my-ws/types/epic/properties/url-confluence',
        { label: 'URL Confluence', type: 'text' },
      ),
    )
  })

  it('transition de type refusée (données existantes) : le 422 du backend s’affiche', async () => {
    renderWithProviders()
    fireEvent.click(await screen.findByTestId('type-row-epic'))
    fireEvent.click(await screen.findByTestId('edit-prop-url-confluence'))
    vi.mocked(api.patch).mockRejectedValue(
      new Error("type non modifiable : 3 valeur(s) existante(s) — transitions permises depuis 'url' : restricted_list, text"),
    )
    fireEvent.change(screen.getByTestId('edit-prop-type'), { target: { value: 'int' } })
    fireEvent.click(screen.getByTestId('edit-prop-save'))
    expect(await screen.findByTestId('edit-prop-error')).toHaveTextContent('transitions permises')
  })

  it('clic sur la ligne → panneau sous la ligne ; reclic, Échap et bouton ferment', async () => {
    renderWithProviders()
    const row = await screen.findByTestId('type-row-epic')
    fireEvent.click(row)
    expect(await screen.findByTestId('close-panel-epic')).toBeInTheDocument()
    // Reclic de la ligne → fermé.
    fireEvent.click(row)
    expect(screen.queryByTestId('close-panel-epic')).not.toBeInTheDocument()
    // Échap → fermé.
    fireEvent.click(row)
    expect(await screen.findByTestId('close-panel-epic')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() =>
      expect(screen.queryByTestId('close-panel-epic')).not.toBeInTheDocument(),
    )
    // Bouton fermer → fermé.
    fireEvent.click(row)
    fireEvent.click(await screen.findByTestId('close-panel-epic'))
    expect(screen.queryByTestId('close-panel-epic')).not.toBeInTheDocument()
  })

  it('supprimer une valeur utilisée : confirmation puis 409 avec le décompte', async () => {
    vi.mocked(api.delete).mockRejectedValue(new Error('valeur utilisée par 3 document(s) existant(s)'))
    renderWithProviders()
    fireEvent.click(await screen.findByTestId('type-row-epic'))
    fireEvent.click(await screen.findByTestId('delete-val-statut-fait'))
    // Confirmation d'abord (verbe explicite), pas de suppression muette.
    const dialog = await screen.findByTestId('delete-val-dialog')
    expect(dialog).toHaveTextContent('Fait')
    fireEvent.click(screen.getByTestId('delete-val-dialog-confirm'))
    // Le refus de l'API (valeur utilisée) est affiché AVEC le nombre concerné.
    await waitFor(() =>
      expect(screen.getByTestId('delete-val-dialog-error')).toHaveTextContent('3 document(s)'),
    )
  })

  it('ajouter une propriété obligatoire signale les documents qui deviennent incomplets', async () => {
    renderWithProviders()
    fireEvent.click(await screen.findByTestId('type-row-epic'))
    fireEvent.click(await screen.findByTestId('add-prop-epic'))
    // Sans « obligatoire » : aucun avertissement.
    expect(screen.queryByTestId('required-warn-epic')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('prop-required-epic'))
    expect(await screen.findByTestId('required-warn-epic'))
      .toHaveTextContent('5 documents de ce type deviendront incomplets')
  })

  it('l’ajout de propriété envoie libellé, type scalaire et obligatoire', async () => {
    vi.mocked(api.post).mockResolvedValue({})
    renderWithProviders()
    fireEvent.click(await screen.findByTestId('type-row-epic'))
    fireEvent.click(await screen.findByTestId('add-prop-epic'))
    fireEvent.change(screen.getByLabelText('Libellé'), { target: { value: 'Deadline' } })
    fireEvent.change(screen.getByTestId('prop-type-select-epic'), { target: { value: 'date' } })
    fireEvent.click(screen.getByTestId('prop-required-epic'))
    fireEvent.click(screen.getByTestId('confirm-add-prop-epic'))
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/workspaces/my-ws/types/epic/properties', {
        slug: 'deadline', label: 'Deadline', type: 'date', required: true,
      }),
    )
  })

  it('le nuancier de couleurs est celui du système (pas de pipette libre)', async () => {
    renderWithProviders()
    fireEvent.click(await screen.findByTestId('type-row-epic'))
    fireEvent.click(await screen.findByTestId('add-val-statut'))
    const swatches = screen.getByTestId('new-val-color')
    expect(swatches.querySelectorAll('[role="radio"]')).toHaveLength(5)
    expect(document.querySelector('input[type="color"]')).toBeNull()
  })
})

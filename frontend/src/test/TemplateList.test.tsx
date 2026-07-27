import { render, screen, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import '../lib/i18n'
import TemplateList, { normalizeSourceUrl } from '../pages/TemplateList'
import { api, galleryApi, templatesApi } from '../lib/api'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    templatesApi: { getYaml: vi.fn(), saveYaml: vi.fn(), delete: vi.fn() },
    galleryApi: {
      listSources: vi.fn(),
      addSource: vi.fn(),
      deleteSource: vi.fn(),
      list: vi.fn(),
      pull: vi.fn(),
      pullDiff: vi.fn(),
    },
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
    blocks_count: 3,
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

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(galleryApi.listSources).mockResolvedValue([])
})

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

// ── Écran Templates Broadsheet : DoD ─────────────────────────────────────────

import { fireEvent } from '@testing-library/react'

describe('TemplateList — DoD Broadsheet', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.get).mockResolvedValue(mockTemplates)
    vi.mocked(galleryApi.listSources).mockResolvedValue([
      { id: 's1', label: 'Galerie yoops', url: 'https://raw.example/tpl', builtin: false },
    ])
    vi.mocked(galleryApi.list).mockResolvedValue([
      {
        template: 'agile-basic', label: 'Projet agile', version: 2,
        type_slugs: ['epic'], concrete_types: 1, installed: true, update_available: true,
      },
    ])
  })

  it('la ligne installée porte le nombre de blocs utilisateurs', async () => {
    render(wrapper(<TemplateList />))
    expect(await screen.findByTestId('tpl-blocks-agile-basic')).toHaveTextContent('3 blocs')
  })

  it('supprimer un template utilisé : refus avec la liste des blocs', async () => {
    vi.mocked(templatesApi.delete).mockRejectedValue(
      new Error('template utilisé par 3 bloc(s) — ws-a / Backlog, ws-a / Specs, ws-b / Docs'),
    )
    render(wrapper(<TemplateList />))
    fireEvent.click(await screen.findByTestId('delete-btn-agile-basic'))
    // L'impact (blocs utilisateurs) est annoncé AVANT le clic destructeur.
    expect(await screen.findByTestId('delete-modal-impact')).toHaveTextContent('3 blocs')
    fireEvent.click(screen.getByTestId('delete-confirm-btn'))
    await waitFor(() =>
      expect(screen.getByTestId('delete-modal-error')).toHaveTextContent('ws-a / Backlog'),
    )
  })

  it('mettre à jour montre le diff (types / propriétés ajoutés) avant confirmation', async () => {
    vi.mocked(galleryApi.pullDiff).mockResolvedValue({
      template: 'agile-basic', installed_version: 1, remote_version: 2,
      new_types: ['bug'], new_properties: ['epic.priorite'],
    })
    vi.mocked(galleryApi.pull).mockResolvedValue({ ...mockTemplates[0], version: 2 })
    render(wrapper(<TemplateList />))

    fireEvent.click(await screen.findByTestId('gallery-install-agile-basic'))
    // AUCUNE écriture avant la confirmation : seul le diff a été demandé.
    const dialog = await screen.findByTestId('update-diff-dialog')
    expect(galleryApi.pull).not.toHaveBeenCalled()
    expect(dialog).toHaveTextContent('Version 1 → 2')
    expect(dialog).toHaveTextContent('bug')
    expect(dialog).toHaveTextContent('epic.priorite')

    fireEvent.click(screen.getByTestId('update-diff-dialog-confirm'))
    await waitFor(() =>
      expect(galleryApi.pull).toHaveBeenCalledWith('https://raw.example/tpl', 'agile-basic'),
    )
  })

  it("l'installation d'un template absent reste directe (pas de diff inutile)", async () => {
    vi.mocked(galleryApi.list).mockResolvedValue([
      {
        template: 'kanban', label: 'Kanban', version: 1,
        type_slugs: ['carte'], concrete_types: 1, installed: false, update_available: false,
      },
    ])
    vi.mocked(galleryApi.pull).mockResolvedValue({
      template: 'kanban', label: 'Kanban', version: 1, path: 'kanban.yaml',
      concrete_types: 1, type_slugs: ['carte'], blocks_count: 0,
    })
    render(wrapper(<TemplateList />))
    fireEvent.click(await screen.findByTestId('gallery-install-kanban'))
    await waitFor(() => expect(galleryApi.pull).toHaveBeenCalled())
    expect(galleryApi.pullDiff).not.toHaveBeenCalled()
  })
})

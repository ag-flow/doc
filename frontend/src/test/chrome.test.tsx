import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import '../lib/i18n'
import { truncateMiddle } from '../lib/truncateMiddle'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    api: { get: vi.fn() },
    docsApi: { getBlocks: vi.fn(), getDocument: vi.fn() },
    referencesApi: { searchGlobal: vi.fn() },
    isSuperAdmin: () => true,
    clearToken: vi.fn(),
  }
})

import { api, docsApi } from '../lib/api'
import { AppRail } from '../components/AppRail'
import { AppHeader } from '../components/AppHeader'

const WS = { slug: 'prod', label: 'Documentation produit', description: null, archived: false }
const BLOCKS = [{ slug: 'specs', label: 'Spécifications', functional_type_slug: 'epic' }]

function renderAt(path: string, element: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(
    [{ path: '*', element: <QueryClientProvider client={qc}>{element}</QueryClientProvider> }],
    { initialEntries: [path] },
  )
  return render(<RouterProvider router={router} />)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.get).mockImplementation((url: string) =>
    Promise.resolve((url === '/workspaces' ? [WS] : WS) as never),
  )
  vi.mocked(docsApi.getBlocks).mockResolvedValue(BLOCKS as never)
})

describe('rail de navigation', () => {
  it('garde son état actif sur navigation directe par URL', async () => {
    renderAt('/ws/prod/automations', <AppRail />)
    const active = await screen.findByTitle('Automates')
    expect(active).toHaveAttribute('aria-current', 'page')
    // Une seule entrée active à la fois.
    const rail = screen.getByTestId('app-rail')
    expect(rail.querySelectorAll('[aria-current="page"]')).toHaveLength(1)
  })

  it('les entrées de workspace n’apparaissent qu’en contexte de workspace', () => {
    renderAt('/templates', <AppRail />)
    expect(screen.queryByTitle('Automates')).not.toBeInTheDocument()
    expect(screen.getByTitle('Workspaces')).toBeInTheDocument()
  })

  it('« Documents » est désactivé hors bloc, actif dans un bloc', () => {
    const { unmount } = renderAt('/ws/prod/blocs', <AppRail />)
    expect(screen.getByTitle('Documents (choisir un bloc)')).toHaveAttribute('aria-disabled', 'true')
    unmount()
    renderAt('/ws/prod/blocs/specs/documents', <AppRail />)
    expect(screen.getByTitle('Documents')).toHaveAttribute('href', '/ws/prod/blocs/specs/documents')
  })

  it('cible de clic ≥ 40px : la largeur vient du token, pas d’une valeur locale', () => {
    const tokens = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf-8')
    const target = /--rail-target:\s*(\d+)px/.exec(tokens)
    expect(target).not.toBeNull()
    expect(Number(target![1])).toBeGreaterThanOrEqual(40)
    const chrome = readFileSync(join(process.cwd(), 'src/styles/chrome.css'), 'utf-8')
    expect(chrome).toMatch(/\.rail-btn\s*\{[^}]*width:\s*var\(--rail-target\)/)
    expect(chrome).toMatch(/\.rail-btn\s*\{[^}]*height:\s*var\(--rail-target\)/)
  })
})

describe('en-tête et fil d’Ariane', () => {
  it('rend la tête de journal (filet gras + filet fin) sur tout écran', () => {
    const { container } = renderAt('/templates', <AppHeader />)
    expect(container.querySelector('.header-rule-thick')).not.toBeNull()
    expect(container.querySelector('.header-rule-thin')).not.toBeNull()
    // Un écran hors workspace a quand même son segment.
    expect(screen.getByText('Templates')).toBeInTheDocument()
  })

  it('workspace / bloc : le dernier segment est la page courante, non cliquable', async () => {
    renderAt('/ws/prod/blocs/specs/documents', <AppHeader />)
    const ws = await screen.findByText('Documentation produit')
    expect(ws.tagName).toBe('A')
    const bloc = screen.getByText('Spécifications')
    expect(bloc.tagName).toBe('SPAN')
    expect(bloc).toHaveClass('crumb-current')
  })

  it('affiche la section du workspace quand il n’y a pas de bloc', async () => {
    renderAt('/ws/prod/types', <AppHeader />)
    await waitFor(() => expect(screen.getByText('Types fonctionnels')).toBeInTheDocument())
  })
})

describe('troncature au milieu', () => {
  it('laisse court un libellé court', () => {
    expect(truncateMiddle('Spécifications')).toBe('Spécifications')
  })

  it('coupe au milieu et garde la fin distinctive', () => {
    const long = 'MPTS — Types scalaires de propriétés fonctionnelles (v2)'
    const out = truncateMiddle(long, 34)
    expect(out).toHaveLength(34)
    expect(out).toContain('…')
    expect(out.startsWith('MPTS')).toBe(true)
    expect(out.endsWith('(v2)')).toBe(true)
  })

  it('le titre complet reste disponible en infobulle', async () => {
    const long = 'Un titre de document délibérément très long pour être tronqué'
    vi.mocked(docsApi.getDocument).mockResolvedValue({
      doc_technical_key: 'd1', title: long, parent_id: null, version: 1,
    } as never)
    renderAt('/ws/prod/blocs/specs/documents/d1', <AppHeader />)
    const el = await screen.findByTitle(long)
    expect(el.textContent).toContain('…')
    expect(el.textContent!.length).toBeLessThan(long.length)
  })
})

describe('recherche globale (en-tête)', () => {
  it('Cmd/Ctrl+K ouvre la palette ; Échap la ferme et rend le focus au déclencheur', async () => {
    renderAt('/templates', <AppHeader />)
    const trigger = screen.getByTestId('open-search-btn')
    trigger.focus()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(await screen.findByTestId('command-palette')).toBeInTheDocument()
    fireEvent.keyDown(screen.getByTestId('palette-input'), { key: 'Escape' })
    await waitFor(() =>
      expect(screen.queryByTestId('command-palette')).not.toBeInTheDocument(),
    )
    expect(trigger).toHaveFocus()
  })
})

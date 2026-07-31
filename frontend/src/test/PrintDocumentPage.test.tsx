import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    docsApi: { ...actual.docsApi, getDocument: vi.fn() },
  }
})

// BlockNote est lourd en jsdom : le viewer est mocké, le contenu passe en texte.
vi.mock('../components/MarkdownViewer', () => ({
  MarkdownViewer: ({ content }: { content: string }) => (
    <div data-testid="markdown-viewer-mock">{content}</div>
  ),
}))

import { docsApi, type DocumentOut } from '../lib/api'
import { WorkspaceProvider } from '../contexts/WorkspaceContext'
import { PrintDocumentPage, fitFactor, computeCuts, type FlowBlock } from '../pages/PrintDocumentPage'

function doc(id: string, title: string, content: string): DocumentOut {
  return {
    doc_technical_key: id, title, type: 'md', slug: null, content, version: 1,
    parent_id: null, functional_type_slug: null, workspace_slug: 'w',
    data_block_ref: 'b', exposed: false, created_at: '', updated_at: '', updated_by: null,
  }
}

function renderAt(url: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceProvider>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route
              path="/ws/:wsSlug/blocs/:blocSlug/documents/:docId/print"
              element={<PrintDocumentPage />}
            />
          </Routes>
        </MemoryRouter>
      </WorkspaceProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(docsApi.getDocument).mockImplementation(async (_ws: string, id: string) => {
    if (id === 'root') return doc('root', 'Racine', '# Racine\n\nCorps racine.')
    if (id === 'c2') return doc('c2', 'Enfant 2', 'Corps 2.')
    if (id === 'c1') return doc('c1', 'Enfant 1', 'Corps 1.')
    throw new Error('inconnu')
  })
})

describe('PrintDocumentPage', () => {
  it('rend le document puis les enfants DANS L’ORDRE de l’URL, titre dédoublonné', async () => {
    renderAt('/ws/w/blocs/blk/documents/root/print?children=c2,c1')
    await waitFor(() => expect(screen.getByTestId('print-doc-root')).toBeInTheDocument())
    const sections = screen.getAllByTestId(/^print-doc-/)
    expect(sections.map((s) => s.getAttribute('data-testid'))).toEqual([
      'print-doc-root', 'print-doc-c2', 'print-doc-c1',
    ])
    // Le « # Racine » de tête est retiré (le titre est déjà rendu en h1).
    expect(sections[0]).toHaveTextContent('Corps racine.')
    expect(sections[0].querySelector('[data-testid="markdown-viewer-mock"]')).not.toHaveTextContent('# Racine')
    // Saut de page avant chaque document suivant, pas le premier.
    expect(sections[0].className).not.toContain('print-break')
    expect(sections[1].className).toContain('print-break')
    expect(screen.queryByTestId('print-signatures')).not.toBeInTheDocument()
  })

  it('chaque document suivant démarre sur une nouvelle page (repère de remplissage)', async () => {
    renderAt('/ws/w/blocs/blk/documents/root/print?children=c2,c1')
    await waitFor(() => expect(screen.getByTestId('print-doc-root')).toBeInTheDocument())
    // Le premier document n'a pas de saut ; chaque suivant est précédé d'un
    // remplissage « page suivante ».
    expect(screen.queryByTestId('page-fill-root')).not.toBeInTheDocument()
    expect(screen.getByTestId('page-fill-c2')).toBeInTheDocument()
    expect(screen.getByTestId('page-fill-c1')).toBeInTheDocument()
    // Le remplissage précède bien sa section dans l'ordre du document.
    const fill = screen.getByTestId('page-fill-c2')
    const section = screen.getByTestId('print-doc-c2')
    expect(fill.compareDocumentPosition(section) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('signed=true ajoute le cadre de signatures ; le bouton lance window.print', async () => {
    const printSpy = vi.fn()
    vi.stubGlobal('print', printSpy)
    renderAt('/ws/w/blocs/blk/documents/root/print?signed=true')
    await waitFor(() => expect(screen.getByTestId('print-doc-root')).toBeInTheDocument())
    expect(screen.getByTestId('print-signatures')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('print-btn'))
    expect(printSpy).toHaveBeenCalled()
  })

  it('un document introuvable → message d’erreur, pas de crash', async () => {
    renderAt('/ws/w/blocs/blk/documents/root/print?children=fantome')
    await waitFor(() => expect(screen.getByTestId('print-error')).toBeInTheDocument())
    expect(screen.getByTestId('print-doc-root')).toBeInTheDocument()
  })
})

describe('fitFactor — réduction des composants plus hauts qu’une page', () => {
  it('tient sur la page → aucun zoom', () => {
    expect(fitFactor(500, 1000)).toBe(1)
    expect(fitFactor(1000, 1000)).toBe(1)
  })
  it('dépasse → réduit pour tenir avec 4 % de marge', () => {
    expect(fitFactor(2000, 1000)).toBeCloseTo(0.48, 2)
  })
  it('borné à 35 % — jamais illisible', () => {
    expect(fitFactor(100000, 1000)).toBe(0.35)
  })
})

describe('computeCuts — repères de coupure fidèles', () => {
  const P = 1000

  it('contenu sécable uniforme → coupures naïves tous les pageH', () => {
    const blocks: FlowBlock[] = [{ top: 0, bottom: 2500, kind: 'break' }]
    expect(computeCuts(blocks, P, 2500)).toEqual([1000, 2000])
  })

  it('coupure dans un composant → reculée avant le composant', () => {
    const blocks: FlowBlock[] = [
      { top: 0, bottom: 900, kind: 'break' },
      { top: 900, bottom: 1400, kind: 'component' }, // 900<1000<1400 : la naïve tranche
    ]
    // Pas de titre : on recule juste avant le composant.
    expect(computeCuts(blocks, P, 1400)).toEqual([900])
  })

  it('titre + composant (cas capture) → coupure reculée avant le TITRE', () => {
    const blocks: FlowBlock[] = [
      { top: 0, bottom: 900, kind: 'break' }, // corps page 1
      { top: 900, bottom: 970, kind: 'heading' }, // « Ce que ça permet »
      { top: 970, bottom: 1400, kind: 'component' }, // le tableau
    ]
    expect(computeCuts(blocks, P, 1400)).toEqual([900])
  })

  it('titre suivi d’un paragraphe (pas orphelin) → coupure naïve conservée', () => {
    const blocks: FlowBlock[] = [
      { top: 0, bottom: 940, kind: 'break' },
      { top: 940, bottom: 990, kind: 'heading' },
      { top: 990, bottom: 1600, kind: 'break' }, // paragraphe traversant la coupure
    ]
    // Le titre n’est pas dernier (le paragraphe le suit sur la page) → 1000.
    expect(computeCuts(blocks, P, 1600)).toEqual([1000])
  })

  it('composant plus grand qu’une page en tête de page → repli naïf (pas de boucle)', () => {
    const blocks: FlowBlock[] = [{ top: 0, bottom: 2500, kind: 'component' }]
    expect(computeCuts(blocks, P, 2500)).toEqual([1000, 2000])
  })
})

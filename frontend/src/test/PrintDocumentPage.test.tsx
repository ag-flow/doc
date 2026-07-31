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
import { PrintDocumentPage, fitFactor } from '../pages/PrintDocumentPage'

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

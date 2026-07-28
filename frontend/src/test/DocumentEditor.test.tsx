import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

// BlockNote est lourd à charger en jsdom : on mocke le wrapper éditeur.
vi.mock('../components/MarkdownEditor', () => ({
  MarkdownEditor: React.forwardRef(
    (
      { initialContent }: { initialContent?: string; onDirty?: () => void },
      ref: React.Ref<{ getMarkdown: () => Promise<string> }>,
    ) => {
      React.useImperativeHandle(ref, () => ({
        getMarkdown: () => Promise.resolve(initialContent ?? ''),
      }))
      return <div data-testid="markdown-editor-mock">{initialContent}</div>
    },
  ),
}))

// PropertiesPanel charge ses propres requêtes : on le mocke pour isoler l'éditeur.
vi.mock('../components/PropertiesPanel', () => ({
  PropertiesPanel: () => <div data-testid="properties-panel-mock" />,
}))

// DocumentChildrenPanel fait ses propres requêtes : on le mocke pour isoler l'éditeur.
vi.mock('../components/DocumentChildrenPanel', () => ({
  DocumentChildrenPanel: () => <div data-testid="children-panel-mock" />,
}))

// MarkdownViewer (mode lecture) monte BlockNote, lourd en jsdom : on le mocke.
vi.mock('../components/MarkdownViewer', () => ({
  MarkdownViewer: ({ content }: { content: string }) => (
    <div data-testid="markdown-viewer-mock">{content}</div>
  ),
}))

// CodeMirror ne fonctionne pas en jsdom : on substitue des implémentations minimales.
vi.mock('@codemirror/merge', () => ({
  unifiedMergeView: () => [],
}))
vi.mock('codemirror', () => ({
  basicSetup: [],
  EditorView: class {
    state = { doc: { toString: () => '' } }
    constructor(_config: unknown) {}
    destroy() {}
  },
}))
vi.mock('@codemirror/lang-markdown', () => ({ markdown: () => [] }))
vi.mock('@codemirror/state', () => ({
  EditorState: { readOnly: { of: () => [] } },
}))
vi.mock('@codemirror/view', () => ({
  EditorView: { editable: { of: () => [] } },
}))

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    ApiError: actual.ApiError,
    docsApi: {
      ...actual.docsApi,
      getDocument: vi.fn(),
      patchDocument: vi.fn(),
    },
  }
})

import { docsApi, ApiError, type DocumentOut } from '../lib/api'
import { DocumentEditor } from '../pages/DocumentEditor'

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(
    [{ path: '/ws/:wsSlug/blocs/:blocSlug/documents/:docId', element: <DocumentEditor /> }],
    { initialEntries: ['/ws/ws/blocs/b1/documents/d1'] },
  )
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

// Le mode lecture « wiki » est celui par défaut : on bascule en édition pour
// exercer les scénarios d'édition / sauvegarde / conflit.
async function enterEditMode() {
  await waitFor(() =>
    expect(screen.getByTestId('document-edit-btn')).toBeInTheDocument(),
  )
  await act(async () => {
    fireEvent.click(screen.getByTestId('document-edit-btn'))
  })
  await waitFor(() =>
    expect(screen.getByTestId('document-editor')).toBeInTheDocument(),
  )
}

const doc: DocumentOut = {
  doc_technical_key: 'd1',
  title: 'Mon document',
  type: 'page',
  slug: null,
  content: '# Hello',
  version: 3,
  parent_id: null,
  functional_type_slug: 'epic',
  workspace_slug: 'ws',
  data_block_ref: 'b1',
  exposed: false,
  created_at: '',
  updated_at: '',
  updated_by: null,
}

describe('DocumentEditor', () => {
  beforeEach(() => vi.clearAllMocks())

  // Lecture « wiki » par défaut à l'ouverture
  it('opens in read mode by default and renders the title as a heading', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    renderEditor()
    await waitFor(() =>
      expect(screen.getByTestId('document-reader')).toBeInTheDocument(),
    )
    expect(screen.getByRole('heading', { name: 'Mon document' })).toBeInTheDocument()
    expect(screen.getByTestId('markdown-viewer-mock')).toBeInTheDocument()
    // Pas d'éditeur tant qu'on n'a pas cliqué sur « Éditer »
    expect(screen.queryByTestId('document-editor')).not.toBeInTheDocument()
  })

  // DoD 24.1 — chargement + affichage (après passage en édition)
  it('loads the document and shows the title', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    renderEditor()
    await enterEditMode()
    expect(screen.getByDisplayValue('Mon document')).toBeInTheDocument()
    expect(screen.getByTestId('markdown-editor-mock')).toBeInTheDocument()
    expect(screen.getByTestId('document-save-btn')).toBeInTheDocument()
  })

  // DoD 24.2 — sauvegarde avec le contenu éditeur
  it('saves document on button click', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    vi.mocked(docsApi.patchDocument).mockResolvedValue({ ...doc, version: 4 })

    renderEditor()
    await enterEditMode()

    // Modifier le titre pour passer en dirty (le bouton devient actif)
    fireEvent.change(screen.getByTestId('document-title-input'), {
      target: { value: 'Mon document modifié' },
    })
    await waitFor(() =>
      expect(screen.getByTestId('document-save-btn')).not.toBeDisabled(),
    )

    await act(async () => {
      fireEvent.click(screen.getByTestId('document-save-btn'))
    })

    await waitFor(() =>
      expect(vi.mocked(docsApi.patchDocument)).toHaveBeenCalledWith(
        'ws',
        'd1',
        expect.objectContaining({ expected_version: 3 }),
      ),
    )
  })

  // DoD 24.3 — 409 → ConflictResolver s'ouvre
  it('opens ConflictResolver on 409', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    vi.mocked(docsApi.patchDocument).mockRejectedValue(
      new ApiError(
        409,
        { title: 'Serveur', content: '# Serveur', version: 4 },
        'Conflit de version',
      ),
    )

    renderEditor()
    await enterEditMode()

    // Modifier le titre pour passer en dirty
    fireEvent.change(screen.getByTestId('document-title-input'), {
      target: { value: 'Mon document modifié' },
    })
    await waitFor(() =>
      expect(screen.getByTestId('document-save-btn')).not.toBeDisabled(),
    )

    await act(async () => {
      fireEvent.click(screen.getByTestId('document-save-btn'))
    })

    // ConflictResolver doit s'afficher
    await waitFor(() =>
      expect(screen.getByText('Conflit de version')).toBeInTheDocument(),
    )
  })
})

// ── Écran document Broadsheet : feuille partagée, Cmd+S, pas de débordement ──

describe('DocumentEditor — ossature Broadsheet', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lecture et édition rendent la MÊME feuille (aucun décalage du texte)', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    const { container } = renderEditor()

    const readSheet = await waitFor(() => {
      const el = container.querySelector('.doc-sheet')
      expect(el).not.toBeNull()
      return el!
    })
    const readShell = readSheet.parentElement?.parentElement?.className
    const readClasses = readSheet.className

    await enterEditMode()
    const editSheet = container.querySelector('.doc-sheet')!
    // Même classe de feuille et même conteneur de grille : les métriques (mesure,
    // interlignage, marges) viennent d'une seule source, donc rien ne bouge.
    // Seule exception voulue : le sommaire (doc-grid-nav) n'existe qu'en lecture.
    const dropNav = (cls?: string) => (cls ?? '').replace(' doc-grid-nav', '')
    expect(editSheet.className).toBe(readClasses)
    expect(dropNav(editSheet.parentElement?.parentElement?.className)).toBe(dropNav(readShell))
  })

  it('Cmd/Ctrl+S enregistre et affiche un accusé discret (pas de toast)', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    vi.mocked(docsApi.patchDocument).mockResolvedValue({ ...doc, version: 4 })
    renderEditor()
    await enterEditMode()

    // Rendre le document « sale » pour que la sauvegarde ait lieu.
    fireEvent.change(screen.getByTestId('document-title-input'), {
      target: { value: 'Mon document modifié' },
    })
    expect(screen.getByTestId('document-dirty')).toBeInTheDocument()

    await act(async () => {
      fireEvent.keyDown(window, { key: 's', ctrlKey: true })
    })
    await waitFor(() => expect(docsApi.patchDocument).toHaveBeenCalledTimes(1))

    // Accusé en place de « non enregistré », dans le flux — aucun dialogue.
    const ack = await screen.findByTestId('document-saved')
    expect(ack).toHaveTextContent('Enregistré')
    expect(screen.queryByTestId('document-dirty')).not.toBeInTheDocument()
    expect(document.querySelector('.dialog-backdrop')).toBeNull()
  })
})

describe('feuille document — aucun débordement horizontal possible', () => {
  // jsdom ne calcule pas de layout : on verrouille les règles CSS qui empêchent
  // le débordement, seul garde-fou automatisable.
  const css = readFileSync(join(process.cwd(), 'src/styles/document.css'), 'utf-8')

  it('la colonne de texte a un minimum à 0 (sinon un tableau large pousse la page)', () => {
    expect(css).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)/)
    // Panneaux flottants : le shell réserve leur espace par padding — s'ils
    // sont fixes sans padding réservé, ils recouvrent le texte.
    expect(css).toMatch(/\.doc-shell-nav\s*\{\s*padding-left/)
    expect(css).toMatch(/\.doc-shell-aside\s*\{\s*padding-right/)
    expect(css).toMatch(/\.doc-aside\s*\{[^}]*position:\s*fixed/)
    expect(css).toMatch(/\.doc-nav-col\s*\{[^}]*position:\s*fixed/)
  })

  it('tableaux, blocs de code et images sont contenus dans la feuille', () => {
    expect(css).toMatch(/\.doc-sheet table\s*\{[^}]*overflow-x:\s*auto/)
    expect(css).toMatch(/\.doc-sheet table\s*\{[^}]*max-width:\s*100%/)
    expect(css).toMatch(/\.doc-sheet pre\s*\{[^}]*overflow-x:\s*auto/)
    expect(css).toMatch(/\.doc-sheet img\s*\{[^}]*max-width:\s*100%/)
  })
})

describe('lecture — pas de titre en double', () => {
  it('un corps commençant par « # <titre> » ne répète pas le titre du shell', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue({
      ...doc,
      title: 'Mon document',
      content: '# Mon document\n\nLe vrai contenu.',
    })
    renderEditor()
    await waitFor(() => expect(screen.getByTestId('document-reader')).toBeInTheDocument())
    const body = screen.getByTestId('markdown-viewer-mock')
    expect(body.textContent).not.toContain('# Mon document')
    expect(body.textContent).toContain('Le vrai contenu.')
  })

  it('un H1 différent du titre reste affiché (on ne retire que le doublon exact)', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue({
      ...doc,
      title: 'Mon document',
      content: '# Autre chapeau\n\nContenu.',
    })
    renderEditor()
    await waitFor(() => expect(screen.getByTestId('document-reader')).toBeInTheDocument())
    expect(screen.getByTestId('markdown-viewer-mock').textContent).toContain('# Autre chapeau')
  })
})

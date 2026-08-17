import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

// BlockNote est lourd à charger en jsdom : on mocke le wrapper éditeur.
// Fidèle au vrai éditeur : le contenu n'est lu qu'AU MONTAGE — un changement
// ultérieur de la prop (refetch d'arrière-plan) ne recharge rien sans remontage.
vi.mock('../components/MarkdownEditor', () => ({
  MarkdownEditor: React.forwardRef(
    (
      { initialContent }: { initialContent?: string; onDirty?: () => void },
      ref: React.Ref<{ getMarkdown: () => Promise<string> }>,
    ) => {
      const [content] = React.useState(initialContent ?? '')
      React.useImperativeHandle(ref, () => ({
        getMarkdown: () => Promise.resolve(content),
      }))
      return <div data-testid="markdown-editor-mock">{content}</div>
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
      deleteDocument: vi.fn(),
    },
  }
})

import { docsApi, ApiError, type DocumentOut } from '../lib/api'
// Le suivi SSE est mocké : on capture les handlers pour simuler les événements.
vi.mock('../lib/docWatch', () => ({
  watchDocument: vi.fn(() => () => {}),
}))

import { watchDocument } from '../lib/docWatch'
import { ToastProvider } from '../components/Toast'
import { DocumentEditor } from '../pages/DocumentEditor'

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(
    [{ path: '/ws/:wsSlug/blocs/:blocSlug/documents/:docId', element: <DocumentEditor /> }],
    { initialEntries: ['/ws/ws/blocs/b1/documents/d1'] },
  )
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
    qc,
    router,
  }
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

// ── Live-reload (phase A) : suivi SSE branché sur les deux modes ──

describe('DocumentEditor — live-reload (phase A)', () => {
  beforeEach(() => vi.clearAllMocks())

  function lastHandlers() {
    const calls = vi.mocked(watchDocument).mock.calls
    return calls[calls.length - 1][2]
  }

  it('lecture : un change distant re-fetch le document (rendu auto)', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    renderEditor()
    await waitFor(() => expect(screen.getByTestId('document-reader')).toBeInTheDocument())
    expect(watchDocument).toHaveBeenCalledWith('ws', 'd1', expect.anything())
    const before = vi.mocked(docsApi.getDocument).mock.calls.length
    await act(async () => {
      lastHandlers().onChange({ document_id: 'd1', version: 9, updated_at: '', updated_by: 'agent' })
    })
    await waitFor(() =>
      expect(vi.mocked(docsApi.getDocument).mock.calls.length).toBeGreaterThan(before),
    )
  })

  it('édition : un change distant NE recharge rien — toast « modifié par X »', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const router = createMemoryRouter(
      [{ path: '/ws/:wsSlug/blocs/:blocSlug/documents/:docId', element: <DocumentEditor /> }],
      { initialEntries: ['/ws/ws/blocs/b1/documents/d1'] },
    )
    render(
      <QueryClientProvider client={qc}>
        <ToastProvider><RouterProvider router={router} /></ToastProvider>
      </QueryClientProvider>,
    )
    await enterEditMode()
    const before = vi.mocked(docsApi.getDocument).mock.calls.length
    await act(async () => {
      lastHandlers().onChange({ document_id: 'd1', version: 9, updated_at: '', updated_by: 'pocket' })
    })
    expect(await screen.findByText(/modifié par pocket/)).toBeInTheDocument()
    // Aucun re-fetch pendant la saisie.
    expect(vi.mocked(docsApi.getDocument).mock.calls.length).toBe(before)
  })

  it('version distante ≤ locale (écho de sa propre écriture) : ignorée', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    renderEditor()
    await waitFor(() => expect(screen.getByTestId('document-reader')).toBeInTheDocument())
    const before = vi.mocked(docsApi.getDocument).mock.calls.length
    await act(async () => {
      lastHandlers().onChange({ document_id: 'd1', version: 3, updated_at: '', updated_by: 'moi' })
    })
    expect(vi.mocked(docsApi.getDocument).mock.calls.length).toBe(before)
  })
})

// ── Live-reload phase B : fusion three-way au 409 ──

describe('DocumentEditor — fusion automatique (phase B)', () => {
  beforeEach(() => vi.clearAllMocks())

  async function makeDirtyAndSave() {
    fireEvent.change(screen.getByTestId('document-title-input'), {
      target: { value: 'Titre édité' },
    })
    await waitFor(() =>
      expect(screen.getByTestId('document-save-btn')).not.toBeDisabled(),
    )
    await act(async () => {
      fireEvent.click(screen.getByTestId('document-save-btn'))
    })
  }

  it('409 sans conflit réel : le fusionné est enregistré, pas de resolver', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    // Le serveur a ajouté un paragraphe (ours == base : l'éditeur mocké rend
    // initialContent) → fusion = contenu serveur, zéro conflit.
    const serverContent = '# Hello\n\nAjout agent.'
    vi.mocked(docsApi.patchDocument)
      .mockRejectedValueOnce(
        new ApiError(409, { title: 'Mon document', content: serverContent, version: 7 }, 'conflit'),
      )
      .mockResolvedValueOnce({ ...doc, content: serverContent, version: 8 })

    renderEditor()
    await enterEditMode()
    await makeDirtyAndSave()

    await waitFor(() =>
      expect(vi.mocked(docsApi.patchDocument)).toHaveBeenLastCalledWith(
        'ws', 'd1',
        expect.objectContaining({ content: serverContent, expected_version: 7 }),
      ),
    )
    expect(screen.queryByTestId('conflict-resolver')).not.toBeInTheDocument()
  })

  it('re-409 sur l’enregistrement du fusionné : resolver sur l’état frais', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    vi.mocked(docsApi.patchDocument)
      .mockRejectedValueOnce(
        new ApiError(409, { content: '# Hello\n\nAjout agent.', version: 7 }, 'conflit'),
      )
      .mockRejectedValueOnce(
        new ApiError(409, { content: '# Hello\n\nEncore bougé.', version: 9 }, 'conflit'),
      )

    renderEditor()
    await enterEditMode()
    await makeDirtyAndSave()

    await waitFor(() =>
      expect(screen.getByTestId('conflict-resolver')).toBeInTheDocument(),
    )
  })
})

// ── FE-03 durci : un refetch d'arrière-plan pendant l'édition ne doit JAMAIS
//    réaligner le verrou optimiste (expectedVersion / ancestor), même à l'état
//    idle — sinon la sauvegarde suivante écrase une version distante sans 409
//    ni fusion three-way (perte silencieuse d'écritures concurrentes). ──

describe('DocumentEditor — resync gelée en édition (perte concurrente)', () => {
  beforeEach(() => vi.clearAllMocks())

  it("édition à l'état idle : un refetch d'arrière-plan ne réaligne pas expectedVersion — le 409 et la fusion s'engagent", async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    const remoteContent = '# Hello\n\nAjout agent.'
    const { qc } = renderEditor()
    await enterEditMode()

    // Poll du change feed : la v5 distante arrive dans le cache alors que
    // l'éditeur (monté sur la v3) n'est pas remonté — il affiche toujours la v3.
    await act(async () => {
      qc.setQueryData(['document', 'ws', 'd1'], { ...doc, content: remoteContent, version: 5 })
    })
    // Le rendu de la v5 est traité PENDANT l'état idle (c'est le cœur du bug) ;
    // l'éditeur monté sur la v3 n'a pas rechargé le contenu distant.
    await waitFor(() => expect(screen.getByText(/v5/)).toBeInTheDocument())
    expect(screen.getByTestId('markdown-editor-mock')).not.toHaveTextContent('Ajout agent.')

    vi.mocked(docsApi.patchDocument)
      .mockRejectedValueOnce(
        new ApiError(409, { title: 'Mon document', content: remoteContent, version: 5 }, 'conflit'),
      )
      .mockResolvedValueOnce({ ...doc, content: remoteContent, version: 6 })

    fireEvent.change(screen.getByTestId('document-title-input'), {
      target: { value: 'Titre édité' },
    })
    await waitFor(() =>
      expect(screen.getByTestId('document-save-btn')).not.toBeDisabled(),
    )
    await act(async () => {
      fireEvent.click(screen.getByTestId('document-save-btn'))
    })

    await waitFor(() => expect(docsApi.patchDocument).toHaveBeenCalledTimes(2))
    // Cœur du fix : la sauvegarde porte la version réellement éditée (3), pas
    // la v5 du refetch — c'est ce qui force le VRAI 409 côté serveur.
    expect(vi.mocked(docsApi.patchDocument).mock.calls[0][2]).toMatchObject({
      expected_version: 3,
    })
    // Le 409 engage la fusion three-way (base = v3 gelée) : la reprise porte la
    // v5 et CONSERVE l'ajout de l'agent au lieu de l'écraser.
    expect(vi.mocked(docsApi.patchDocument).mock.calls[1][2]).toMatchObject({
      expected_version: 5,
      content: remoteContent,
    })
  })

  it('changement de document : le resync initial a lieu même en mode édition', async () => {
    const doc2: DocumentOut = {
      ...doc, doc_technical_key: 'd2', title: 'Deuxième', content: '# Deux', version: 7,
    }
    vi.mocked(docsApi.getDocument).mockImplementation((_ws: string, id: string) =>
      Promise.resolve(id === 'd2' ? doc2 : doc),
    )
    const { router } = renderEditor()
    await enterEditMode()
    expect(screen.getByDisplayValue('Mon document')).toBeInTheDocument()

    await act(async () => {
      await router.navigate('/ws/ws/blocs/b1/documents/d2')
    })
    // Titre, contenu et verrou réalignés sur le doc chargé.
    await waitFor(() =>
      expect(screen.getByDisplayValue('Deuxième')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('markdown-editor-mock')).toHaveTextContent('# Deux')

    vi.mocked(docsApi.patchDocument).mockResolvedValue({ ...doc2, version: 8 })
    fireEvent.change(screen.getByTestId('document-title-input'), {
      target: { value: 'Deuxième bis' },
    })
    await waitFor(() =>
      expect(screen.getByTestId('document-save-btn')).not.toBeDisabled(),
    )
    await act(async () => {
      fireEvent.click(screen.getByTestId('document-save-btn'))
    })
    await waitFor(() =>
      expect(vi.mocked(docsApi.patchDocument)).toHaveBeenCalledWith(
        'ws', 'd2', expect.objectContaining({ expected_version: 7 }),
      ),
    )
  })

  it('lecture : un refetch réaligne toujours (une version distante déjà connue est ignorée)', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    const { qc } = renderEditor()
    await waitFor(() => expect(screen.getByTestId('document-reader')).toBeInTheDocument())

    await act(async () => {
      qc.setQueryData(['document', 'ws', 'd1'], { ...doc, version: 5 })
    })
    // Attendre que le rendu (et l'effet de resync) de la v5 soit traité.
    await waitFor(() => expect(screen.getByText(/v5/)).toBeInTheDocument())

    const calls = vi.mocked(watchDocument).mock.calls
    const handlers = calls[calls.length - 1][2]
    const before = vi.mocked(docsApi.getDocument).mock.calls.length
    // expectedVersion réaligné sur 5 par le refetch : l'écho v5 est ignoré…
    await act(async () => {
      handlers.onChange({ document_id: 'd1', version: 5, updated_at: '', updated_by: 'agent' })
    })
    expect(vi.mocked(docsApi.getDocument).mock.calls.length).toBe(before)
    // …mais une v6 réellement nouvelle déclenche bien le re-fetch.
    await act(async () => {
      handlers.onChange({ document_id: 'd1', version: 6, updated_at: '', updated_by: 'agent' })
    })
    await waitFor(() =>
      expect(vi.mocked(docsApi.getDocument).mock.calls.length).toBeGreaterThan(before),
    )
  })
})

// ── Double Cmd+S / double clic « Enregistrer » : un seul PATCH en vol ──

describe('DocumentEditor — garde de réentrance de la sauvegarde', () => {
  beforeEach(() => vi.clearAllMocks())

  it('deux Cmd+S rapprochés (avant le re-rendu) n’émettent qu’un seul PATCH', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    vi.mocked(docsApi.patchDocument).mockResolvedValue({ ...doc, version: 4 })
    renderEditor()
    await enterEditMode()

    fireEvent.change(screen.getByTestId('document-title-input'), {
      target: { value: 'Mon document modifié' },
    })
    expect(screen.getByTestId('document-dirty')).toBeInTheDocument()

    // Les deux raccourcis sont dispatchés dans le même tick, avant que React
    // n'ait eu l'occasion de re-rendre avec status='saving' — c'est exactement
    // le scénario du double Cmd+S qui déclenchait deux PATCH concurrents.
    await act(async () => {
      fireEvent.keyDown(window, { key: 's', ctrlKey: true })
      fireEvent.keyDown(window, { key: 's', ctrlKey: true })
    })

    await waitFor(() => expect(docsApi.patchDocument).toHaveBeenCalledTimes(1))
  })
})

// ── Suppression depuis l'éditeur : la liste (browse + requête) doit se
//    rafraîchir aussitôt, pas seulement l'ancienne clé `block-documents` ──

describe('DocumentEditor — invalidation du cache à la suppression', () => {
  beforeEach(() => vi.clearAllMocks())

  it('supprimer un document invalide les mêmes clés que la création (handleCreated)', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    vi.mocked(docsApi.deleteDocument).mockResolvedValue(undefined)

    const { qc } = renderEditor()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    await enterEditMode()

    await act(async () => {
      fireEvent.click(screen.getByTestId('document-delete-btn'))
    })
    await act(async () => {
      fireEvent.click(screen.getByTestId('document-delete-confirm-btn'))
    })

    await waitFor(() => expect(docsApi.deleteDocument).toHaveBeenCalledWith('ws', 'd1'))

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey,
    )
    // Même liste que `handleCreated` de BlockDocumentList (block-type-slugs,
    // block-tree, block-query), plus l'ancienne clé `block-documents`.
    for (const key of [
      ['block-type-slugs', 'ws', 'b1'],
      ['block-tree', 'ws', 'b1'],
      ['block-query', 'ws', 'b1'],
      ['block-documents', 'ws', 'b1'],
    ]) {
      expect(invalidatedKeys).toContainEqual(key)
    }
  })
})

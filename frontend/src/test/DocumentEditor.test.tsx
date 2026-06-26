import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
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
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/ws/ws/blocs/b1/documents/d1']}>
        <Routes>
          <Route
            path="/ws/:wsSlug/blocs/:blocSlug/documents/:docId"
            element={<DocumentEditor />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const doc: DocumentOut = {
  doc_technical_key: 'd1',
  title: 'Mon document',
  type: 'page',
  content: '# Hello',
  version: 3,
  parent_id: null,
  functional_type_slug: 'epic',
  workspace_slug: 'ws',
  data_block_ref: 'b1',
  created_at: '',
  updated_at: '',
}

describe('DocumentEditor', () => {
  beforeEach(() => vi.clearAllMocks())

  // DoD 24.1 — chargement + affichage
  it('loads the document and shows the title', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    renderEditor()
    await waitFor(() =>
      expect(screen.getByTestId('document-editor')).toBeInTheDocument(),
    )
    expect(screen.getByDisplayValue('Mon document')).toBeInTheDocument()
    expect(screen.getByTestId('markdown-editor-mock')).toBeInTheDocument()
    expect(screen.getByTestId('document-save-btn')).toBeInTheDocument()
  })

  // DoD 24.2 — sauvegarde avec le contenu éditeur
  it('saves document on button click', async () => {
    vi.mocked(docsApi.getDocument).mockResolvedValue(doc)
    vi.mocked(docsApi.patchDocument).mockResolvedValue({ ...doc, version: 4 })

    renderEditor()
    await waitFor(() =>
      expect(screen.getByTestId('document-editor')).toBeInTheDocument(),
    )

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
    await waitFor(() =>
      expect(screen.getByTestId('document-editor')).toBeInTheDocument(),
    )

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

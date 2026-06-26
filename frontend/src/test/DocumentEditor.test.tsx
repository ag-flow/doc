import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

// BlockNote est lourd à charger en jsdom : on mocke le wrapper éditeur.
vi.mock('../components/MarkdownEditor', () => ({
  MarkdownEditor: () => <div data-testid="markdown-editor-mock" />,
}))

// PropertiesPanel charge ses propres requêtes : on le mocke pour isoler l'éditeur.
vi.mock('../components/PropertiesPanel', () => ({
  PropertiesPanel: () => <div data-testid="properties-panel-mock" />,
}))

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    docsApi: {
      ...actual.docsApi,
      getDocument: vi.fn(),
      patchDocument: vi.fn(),
    },
  }
})

import { docsApi, type DocumentOut } from '../lib/api'
import { DocumentEditor } from '../pages/DocumentEditor'

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/workspaces/ws/blocks/b1/documents/d1']}>
        <Routes>
          <Route
            path="/workspaces/:ws/blocks/:block/documents/:docId"
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
})

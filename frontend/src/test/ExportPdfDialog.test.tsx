import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    docsApi: { ...actual.docsApi, getBlockDocuments: vi.fn() },
    api: { ...actual.api, getBlob: vi.fn() },
  }
})

import { api, docsApi, type DocumentOut } from '../lib/api'
import { ExportPdfDialog } from '../components/ExportPdfDialog'

function doc(id: string, title: string, parent: string | null): DocumentOut {
  return {
    doc_technical_key: id, title, type: 'md', slug: null, content: null, version: 1,
    parent_id: parent, functional_type_slug: null, workspace_slug: 'w',
    data_block_ref: 'b', exposed: false, created_at: '', updated_at: '', updated_by: null,
  }
}

function renderDialog(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <ExportPdfDialog ws="w" blocSlug="blk" docId="root" filename="mon-doc" onClose={onClose} />
    </QueryClientProvider>,
  )
  return onClose
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([
    doc('root', 'Racine', null),
    doc('c1', 'Enfant 1', 'root'),
    doc('c2', 'Enfant 2', 'root'),
    doc('autre', 'Autre racine', null),
  ])
  vi.mocked(api.getBlob).mockResolvedValue(new Blob(['%PDF-'], { type: 'application/pdf' }))
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:x')
  globalThis.URL.revokeObjectURL = vi.fn()
})

describe('ExportPdfDialog', () => {
  it('document seul : télécharge sans paramètre children', async () => {
    const onClose = renderDialog()
    fireEvent.click(screen.getByTestId('pdf-validate'))
    await waitFor(() =>
      expect(api.getBlob).toHaveBeenCalledWith('/workspaces/w/documents/root/export/pdf'),
    )
    expect(onClose).toHaveBeenCalled()
  })

  it('avec enfants : cochés + réordonnés, dans l’ordre choisi, et signé', async () => {
    renderDialog()
    fireEvent.click(screen.getByTestId('pdf-scope-children'))
    await screen.findByTestId('pdf-child-c1')
    // Décoche c1 puis le recoche ; monte c2 en premier.
    fireEvent.click(screen.getByTestId('pdf-child-up-c2'))
    fireEvent.click(screen.getByTestId('pdf-signed'))
    fireEvent.click(screen.getByTestId('pdf-validate'))
    await waitFor(() =>
      expect(api.getBlob).toHaveBeenCalledWith(
        '/workspaces/w/documents/root/export/pdf?children=c2%2Cc1&signed=true',
      ),
    )
  })

  it('un enfant décoché est exclu', async () => {
    renderDialog()
    fireEvent.click(screen.getByTestId('pdf-scope-children'))
    await screen.findByTestId('pdf-child-c1')
    fireEvent.click(screen.getByTestId('pdf-child-check-c1'))
    fireEvent.click(screen.getByTestId('pdf-validate'))
    await waitFor(() =>
      expect(api.getBlob).toHaveBeenCalledWith(
        '/workspaces/w/documents/root/export/pdf?children=c2',
      ),
    )
  })
})

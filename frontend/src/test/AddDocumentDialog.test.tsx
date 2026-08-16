import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    docsApi: {
      ...actual.docsApi,
      getBlockDocuments: vi.fn(),
      getAllowedTypes: vi.fn(),
      getTypesRich: vi.fn(),
      createDocument: vi.fn(),
    },
  }
})

import { docsApi, type DocumentOut } from '../lib/api'
import { AddDocumentDialog } from '../components/AddDocumentDialog'

function makeDoc(over: Partial<DocumentOut>): DocumentOut {
  return {
    doc_technical_key: 'd1',
    title: 'Doc',
    type: 'page',
    slug: null,
    content: null,
    version: 1,
    parent_id: null,
    functional_type_slug: 'epic',
    workspace_slug: 'ws',
    data_block_ref: 'b1',
    exposed: false,
    created_at: '',
    updated_at: '',
    updated_by: null,
    ...over,
  }
}

function renderDialog(qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(
    <QueryClientProvider client={qc}>
      <AddDocumentDialog
        ws="ws"
        block="b1"
        onCreated={() => {}}
        onClose={() => {}}
      />
    </QueryClientProvider>,
  )
}

describe('AddDocumentDialog — détection de slug dupliqué', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(docsApi.getAllowedTypes).mockResolvedValue([{ slug: 'epic', label: 'Epic' }])
    vi.mocked(docsApi.getTypesRich).mockResolvedValue([])
  })

  // Bug 3 : la page liste (block-tree/block-query) ne peuple plus le cache
  // `block-documents` — le dialog doit charger lui-même les slugs du bloc,
  // pas dépendre d'un cache éventuellement vide.
  it('signale un slug déjà utilisé par un document frère, sans dépendre d’un cache pré-rempli', async () => {
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([
      makeDoc({ doc_technical_key: 'e1', slug: 'existing-slug', parent_id: null }),
    ])

    renderDialog()

    await waitFor(() => expect(screen.getByTestId('add-document-title-input')).toBeInTheDocument())
    await waitFor(() => expect(docsApi.getBlockDocuments).toHaveBeenCalledWith('ws', 'b1'))

    fireEvent.change(screen.getByTestId('add-document-slug-input'), {
      target: { value: 'existing-slug' },
    })

    await waitFor(() =>
      expect(screen.getByText('Ce slug est déjà utilisé par un document du même niveau.'))
        .toBeInTheDocument(),
    )
    expect(screen.getByTestId('add-document-submit')).toBeDisabled()
  })

  it('un slug inédit ne déclenche aucun avertissement', async () => {
    vi.mocked(docsApi.getBlockDocuments).mockResolvedValue([
      makeDoc({ doc_technical_key: 'e1', slug: 'existing-slug', parent_id: null }),
    ])

    renderDialog()

    await waitFor(() => expect(screen.getByTestId('add-document-title-input')).toBeInTheDocument())
    await waitFor(() => expect(docsApi.getBlockDocuments).toHaveBeenCalledWith('ws', 'b1'))
    fireEvent.change(screen.getByTestId('add-document-slug-input'), {
      target: { value: 'un-nouveau-slug' },
    })

    expect(
      screen.queryByText('Ce slug est déjà utilisé par un document du même niveau.'),
    ).not.toBeInTheDocument()
  })
})

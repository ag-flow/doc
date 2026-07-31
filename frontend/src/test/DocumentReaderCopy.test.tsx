import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

// Enfants lourds (BlockNote, panneaux, requêtes) mockés : le test cible la
// barre de méta et le bouton copier.
vi.mock('../components/MarkdownViewer', () => ({ MarkdownViewer: () => <div /> }))
vi.mock('../components/PropertiesPanel', () => ({ PropertiesPanel: () => <div /> }))
vi.mock('../components/BacklinksPanel', () => ({ BacklinksPanel: () => <div /> }))
vi.mock('../components/DocumentChildrenPanel', () => ({ DocumentChildrenPanel: () => <div /> }))
vi.mock('../components/CommentsPanel', () => ({ CommentsPanel: () => <div /> }))
vi.mock('../components/ReactionBar', () => ({ ReactionBar: () => <div /> }))
vi.mock('../components/DocumentTocNav', () => ({
  DocumentToc: () => <div />,
  DocumentPrevNext: () => <div />,
}))
vi.mock('../components/ExportPdfDialog', () => ({ ExportPdfDialog: () => <div /> }))
vi.mock('../lib/api', () => ({
  reactionsApi: {
    getDocReactions: vi.fn().mockResolvedValue({ up: 0, down: 0, mine: 0 }),
    toggleDocReaction: vi.fn(),
  },
}))

import { DocumentReader } from '../components/DocumentReader'
import type { DocumentOut } from '../lib/api'

const doc: DocumentOut = {
  doc_technical_key: 'd1',
  title: 'Résumé',
  type: 'md',
  slug: 'resume',
  content: '# Résumé\n\nCorps du document.',
  version: 6,
  parent_id: null,
  functional_type_slug: 'capture_item',
  workspace_slug: 'docflow',
  data_block_ref: 'b',
  exposed: false,
  created_at: '2026-07-29T10:00:00Z',
  updated_at: '2026-07-29T10:00:00Z',
  updated_by: 'gael',
}

function renderReader() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <DocumentReader ws="docflow" blocSlug="captures" docId="d1" doc={doc} onEdit={() => {}} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.assign(navigator, { clipboard: { writeText } })
  vi.clearAllMocks()
})

describe('DocumentReader — bouton copier le document', () => {
  it('copie le contenu markdown dans le presse-papier et accuse réception', async () => {
    renderReader()
    const btn = screen.getByTestId('copy-document-btn')
    fireEvent.click(btn)
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('# Résumé\n\nCorps du document.')
    await waitFor(() => expect(screen.getByText('Document copié')).toBeInTheDocument())
  })
})

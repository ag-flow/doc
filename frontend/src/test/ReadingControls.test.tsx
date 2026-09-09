import { describe, it, expect, vi, beforeEach } from 'vitest'
import { forwardRef } from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../components/MarkdownViewer', () => ({
  MarkdownViewer: forwardRef(() => <div data-testid="viewer" />),
}))
vi.mock('../components/PropertiesPanel', () => ({
  PropertiesPanel: () => <div data-testid="properties-panel-mock" />,
}))
vi.mock('../components/BacklinksPanel', () => ({ BacklinksPanel: () => <div /> }))
vi.mock('../components/DocumentChildrenPanel', () => ({ DocumentChildrenPanel: () => <div /> }))
vi.mock('../components/CommentsPanel', () => ({ CommentsPanel: () => <div /> }))
vi.mock('../components/ReactionBar', () => ({ ReactionBar: () => <div /> }))
vi.mock('../components/DocumentTocNav', () => ({
  DocumentToc: () => <div data-testid="toc-mock" />,
  DocumentPrevNext: () => <div />,
}))
vi.mock('../components/ExportPdfDialog', () => ({ ExportPdfDialog: () => <div /> }))
vi.mock('../lib/api', () => ({
  reactionsApi: {
    getDocReactions: vi.fn().mockResolvedValue({ up: 0, down: 0, mine: 0 }),
    toggleDocReaction: vi.fn(),
  },
  prefsApi: {
    get: vi.fn().mockResolvedValue({ key: 'reading-prefs', value: null }),
    set: vi.fn().mockResolvedValue({ key: 'reading-prefs', value: null }),
  },
}))

import { DocumentReader } from '../components/DocumentReader'
import { prefsApi, type DocumentOut } from '../lib/api'

const doc: DocumentOut = {
  doc_technical_key: 'd1',
  title: 'Résumé',
  type: 'md',
  slug: 'resume',
  content: '# Résumé\n\nCorps.',
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
  localStorage.clear()
  vi.clearAllMocks()
  vi.mocked(prefsApi.get).mockResolvedValue({ key: 'reading-prefs', value: null })
  vi.mocked(prefsApi.set).mockResolvedValue({ key: 'reading-prefs', value: null })
})

describe('DocumentReader — préférences de lecture', () => {
  it('replie le panneau propriétés et persiste la préférence', async () => {
    renderReader()
    expect(screen.getByTestId('properties-panel-mock')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('props-toggle'))
    await waitFor(() =>
      expect(screen.queryByTestId('properties-panel-mock')).not.toBeInTheDocument(),
    )
    expect(prefsApi.set).toHaveBeenCalledWith(
      'reading-prefs',
      expect.objectContaining({ propsOpen: false }),
    )
  })

  it('mode lecture : replie sommaire ET propriétés en un geste', async () => {
    renderReader()
    expect(screen.getByTestId('toc-mock')).toBeInTheDocument()
    expect(screen.getByTestId('properties-panel-mock')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('reading-mode-toggle'))
    await waitFor(() => expect(screen.queryByTestId('toc-mock')).not.toBeInTheDocument())
    expect(screen.queryByTestId('properties-panel-mock')).not.toBeInTheDocument()
    expect(screen.getByTestId('reading-mode-toggle')).toHaveAttribute('aria-pressed', 'true')
  })

  it('raccourci ⌘/Ctrl + \\ bascule le mode lecture', async () => {
    renderReader()
    fireEvent.keyDown(window, { key: '\\', ctrlKey: true })
    await waitFor(() => expect(screen.queryByTestId('toc-mock')).not.toBeInTheDocument())
  })

  it('l’échelle augmente et est persistée', async () => {
    renderReader()
    expect(screen.getByTestId('scale-reset')).toHaveTextContent('100%')
    fireEvent.click(screen.getByTestId('scale-up'))
    await waitFor(() => expect(screen.getByTestId('scale-reset')).toHaveTextContent('110%'))
    expect(prefsApi.set).toHaveBeenCalledWith(
      'reading-prefs',
      expect.objectContaining({ scaleStep: 3 }),
    )
  })
})

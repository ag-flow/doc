import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    docsApi: { ...actual.docsApi, getBlockTree: vi.fn() },
  }
})

import { docsApi, type BlockTreeNode, type BlockTreePage } from '../lib/api'
import { DocumentToc, DocumentPrevNext } from '../components/DocumentTocNav'

function node(id: string, title: string, children: BlockTreeNode[] = []): BlockTreeNode {
  return {
    id, title, functional_type_slug: null, parent_id: null,
    properties: [], children, updated_at: null, updated_by: null,
  }
}

function page(roots: BlockTreeNode[], has_next = false): BlockTreePage {
  return { block_slug: 'guide', page: 1, page_size: 100, total: roots.length, has_next, roots }
}

function renderWith(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // Arbre : Intro → (Installation → Config) → Usage
  vi.mocked(docsApi.getBlockTree).mockResolvedValue(
    page([node('d1', 'Intro'), node('d2', 'Installation', [node('d3', 'Config')]), node('d4', 'Usage')]),
  )
})

describe('DocumentToc', () => {
  it('liste l’arbre dans l’ordre de lecture, document courant marqué', async () => {
    renderWith(<DocumentToc ws="w" bloc="guide" docId="d3" />)
    const toc = await screen.findByTestId('doc-toc')
    const links = Array.from(toc.querySelectorAll('a'))
    expect(links.map((l) => l.textContent)).toEqual(['Intro', 'Installation', 'Config', 'Usage'])
    expect(links[2]).toHaveAttribute('aria-current', 'page')
    expect(links[2]).toHaveAttribute('href', '/ws/w/blocs/guide/documents/d3')
    expect(links[0]).not.toHaveAttribute('aria-current')
  })
})

describe('DocumentPrevNext', () => {
  it('relie au précédent et au suivant dans l’ordre profond', async () => {
    renderWith(<DocumentPrevNext ws="w" bloc="guide" docId="d3" />)
    const prev = await screen.findByTestId('doc-pagenav-prev')
    expect(prev).toHaveTextContent('Installation')
    expect(prev).toHaveAttribute('href', '/ws/w/blocs/guide/documents/d2')
    const next = screen.getByTestId('doc-pagenav-next')
    expect(next).toHaveTextContent('Usage')
    expect(next).toHaveAttribute('href', '/ws/w/blocs/guide/documents/d4')
  })

  it('premier document : pas de « Précédent »', async () => {
    renderWith(<DocumentPrevNext ws="w" bloc="guide" docId="d1" />)
    await screen.findByTestId('doc-pagenav')
    expect(screen.queryByTestId('doc-pagenav-prev')).not.toBeInTheDocument()
    expect(screen.getByTestId('doc-pagenav-next')).toHaveTextContent('Installation')
  })

  it('document hors du bloc : rien', async () => {
    renderWith(<DocumentPrevNext ws="w" bloc="guide" docId="inconnu" />)
    await vi.waitFor(() => expect(docsApi.getBlockTree).toHaveBeenCalled())
    expect(screen.queryByTestId('doc-pagenav')).not.toBeInTheDocument()
  })
})

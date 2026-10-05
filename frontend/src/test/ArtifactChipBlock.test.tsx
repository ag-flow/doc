import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('../lib/api', () => ({
  artifactsApi: {
    getMeta: vi.fn(),
    getBlob: vi.fn(),
    getLink: vi.fn(),
  },
}))

import { artifactsApi, type ArtifactMetaOut } from '../lib/api'
import { WorkspaceProvider } from '../contexts/WorkspaceContext'
import { ArtifactChipView } from '../components/ArtifactChipBlock'

const ID = '11111111-2222-3333-4444-555555555555'

function meta(over: Partial<ArtifactMetaOut> = {}): ArtifactMetaOut {
  return {
    id: ID,
    filename: 'rapport.pdf',
    extension: 'pdf',
    media_type: 'application/pdf',
    size_bytes: 2048,
    sha256: 'x',
    crc32: 0,
    refcount: 1,
    ...over,
  }
}

function renderChip(label = '') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  // WorkspaceProvider lit le slug depuis localStorage.
  localStorage.setItem('ws_slug', 'w')
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceProvider>
        <ArtifactChipView id={ID} label={label} />
      </WorkspaceProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ArtifactChipView', () => {
  it('affiche le nom de fichier, le type et la taille lisible', async () => {
    vi.mocked(artifactsApi.getMeta).mockResolvedValue(meta())
    renderChip()
    await waitFor(() => expect(screen.getByText('rapport.pdf')).toBeInTheDocument())
    expect(screen.getByText(/PDF · 2\.00 Kio/)).toBeInTheDocument()
  })

  it('un label explicite prime sur le nom de fichier', async () => {
    vi.mocked(artifactsApi.getMeta).mockResolvedValue(meta())
    renderChip('Le contrat')
    await waitFor(() => expect(screen.getByText('Le contrat')).toBeInTheDocument())
  })

  it('Ouvrir demande un lien signé et l’ouvre dans un nouvel onglet', async () => {
    vi.mocked(artifactsApi.getMeta).mockResolvedValue(meta())
    vi.mocked(artifactsApi.getLink).mockResolvedValue({
      url: '/api/workspaces/w/artifacts/' + ID + '/download?exp=1&sig=ab',
      expires_in_seconds: 900,
    })
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    renderChip()
    await waitFor(() => expect(screen.getByTestId('artifact-chip-open')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('artifact-chip-open'))
    await waitFor(() => expect(artifactsApi.getLink).toHaveBeenCalledWith('w', ID))
    await waitFor(() => expect(openSpy).toHaveBeenCalled())
  })

  it('artefact introuvable → état lisible, pas de crash', async () => {
    vi.mocked(artifactsApi.getMeta).mockRejectedValue(new Error('404'))
    renderChip()
    await waitFor(() => expect(screen.getByText(/introuvable/)).toBeInTheDocument())
    expect(screen.getByTestId('artifact-chip-download')).toBeDisabled()
  })
})

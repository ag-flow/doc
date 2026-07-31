import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    artifactTypesApi: {
      adminList: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
    },
  }
})

import { artifactTypesApi, type ArtifactTypeOut } from '../lib/api'
import { ArtifactTypesAdmin } from '../pages/ArtifactTypesAdmin'

function typ(extension: string, media_type: string, label = ''): ArtifactTypeOut {
  return { extension, media_type, label, created_at: '', updated_at: '' }
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ArtifactTypesAdmin />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(artifactTypesApi.adminList).mockResolvedValue([
    typ('pdf', 'application/pdf', 'Document PDF'),
    typ('png', 'image/png', 'Image PNG'),
  ])
})

describe('ArtifactTypesAdmin', () => {
  it('liste les types existants', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('type-row-pdf')).toBeInTheDocument())
    expect(screen.getByText('application/pdf')).toBeInTheDocument()
    expect(screen.getByTestId('type-row-png')).toBeInTheDocument()
  })

  it('ajoute un type via le dialog', async () => {
    vi.mocked(artifactTypesApi.create).mockResolvedValue(typ('heic', 'image/heic', 'HEIC'))
    renderPage()
    await waitFor(() => expect(screen.getByTestId('type-row-pdf')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('add-type-btn'))
    fireEvent.change(screen.getByTestId('type-ext-input'), { target: { value: 'heic' } })
    fireEvent.change(screen.getByTestId('type-mime-input'), { target: { value: 'image/heic' } })
    fireEvent.click(screen.getByTestId('type-save'))

    await waitFor(() =>
      expect(artifactTypesApi.create).toHaveBeenCalledWith({
        extension: 'heic',
        media_type: 'image/heic',
        label: '',
      }),
    )
  })

  it('édition : l’extension est verrouillée', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('type-row-pdf')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('edit-pdf'))
    expect(screen.getByTestId('type-ext-input')).toBeDisabled()
  })

  it('suppression : confirmation puis appel API', async () => {
    vi.mocked(artifactTypesApi.delete).mockResolvedValue(undefined)
    renderPage()
    await waitFor(() => expect(screen.getByTestId('type-row-png')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('delete-png'))
    fireEvent.click(screen.getByTestId('delete-type-dialog-confirm'))
    await waitFor(() => expect(artifactTypesApi.delete).toHaveBeenCalledWith('png'))
  })
})

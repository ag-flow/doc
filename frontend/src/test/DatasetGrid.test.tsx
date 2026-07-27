import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'

vi.mock('../lib/datasetsApi', async () => {
  const actual = await vi.importActual<typeof import('../lib/datasetsApi')>('../lib/datasetsApi')
  return {
    ...actual,
    datasetsApi: {
      getDataset: vi.fn(),
      exportDatasetCsv: vi.fn(),
      importDatasetCsv: vi.fn(),
      addRow: vi.fn(),
      updateRow: vi.fn(),
      deleteRow: vi.fn(),
      addColumn: vi.fn(),
      updateColumn: vi.fn(),
      deleteColumn: vi.fn(),
    },
  }
})

import { datasetsApi, type DatasetDetailOut } from '../lib/datasetsApi'
import { DatasetGrid } from '../components/DatasetGrid'

const detail: DatasetDetailOut = {
  id: 'd1',
  slug: 'ds',
  label: 'Mon tableau',
  columns: [
    { slug: 'name', label: 'Nom', type: 'text', position: 0, required: false },
    { slug: 'age', label: 'Âge', type: 'int', position: 1, required: false },
  ],
  rows: [
    { id: 'r1', cells: { name: 'Alice', age: '30' } },
    { id: 'r2', cells: { name: 'Bob', age: '25' } },
  ],
}

function renderGrid(editable = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <DatasetGrid workspaceSlug="ws" datasetId="d1" editable={editable} />
    </QueryClientProvider>,
  )
}

describe('DatasetGrid', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(datasetsApi.getDataset).mockResolvedValue(detail)
  })

  it('renders dynamic columns and cell values from getDataset (read-only)', async () => {
    renderGrid(false)
    await waitFor(() => expect(screen.getByTestId('dataset-table')).toBeInTheDocument())
    // En-têtes dynamiques
    expect(screen.getByText('Nom')).toBeInTheDocument()
    expect(screen.getByText('Âge')).toBeInTheDocument()
    // Valeurs des cellules (cells[colSlug])
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('25')).toBeInTheDocument()
    expect(datasetsApi.getDataset).toHaveBeenCalledWith('ws', 'd1')
  })

  it('shows editing controls only when editable', async () => {
    renderGrid(true)
    await waitFor(() => expect(screen.getByTestId('dataset-table')).toBeInTheDocument())
    expect(screen.getByTestId('dataset-add-row-btn')).toBeInTheDocument()
    expect(screen.getByTestId('dataset-import-btn')).toBeInTheDocument()
    // Cellules éditables : champs de saisie plutôt que texte brut.
    expect(screen.getByTestId('dataset-cell-name-r1')).toBeInTheDocument()
    expect(screen.getByTestId('dataset-delete-row-r1')).toBeInTheDocument()
  })
})

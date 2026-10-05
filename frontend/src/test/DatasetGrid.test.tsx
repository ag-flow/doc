import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  return {
    qc,
    ...render(
      <QueryClientProvider client={qc}>
        <DatasetGrid workspaceSlug="ws" datasetId="d1" editable={editable} />
      </QueryClientProvider>,
    ),
  }
}

const cell = (testId: string) => screen.getByTestId(testId) as HTMLInputElement

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

  // Régression : deux cellules de la MÊME ligne éditées coup sur coup, avant que le
  // refetch de la première ne soit revenu. Envoyer l'instantané de rendu de toute la
  // ligne faisait repartir l'ancienne valeur de la cellule 1 dans le second PUT —
  // écrasement silencieux. On n'envoie que la cellule modifiée (PATCH partiel).
  it('n’envoie que la cellule modifiée (pas d’écrasement du voisin)', async () => {
    vi.mocked(datasetsApi.updateRow).mockResolvedValue({ row_id: 'r1', updated: true })
    renderGrid(true)
    await waitFor(() => expect(screen.getByTestId('dataset-table')).toBeInTheDocument())

    const name = cell('dataset-cell-name-r1')
    fireEvent.change(name, { target: { value: 'Alicia' } })
    fireEvent.blur(name)

    // Sans attendre le refetch : seconde cellule de la même ligne.
    const age = cell('dataset-cell-age-r1')
    fireEvent.change(age, { target: { value: '31' } })
    fireEvent.blur(age)

    await waitFor(() => expect(datasetsApi.updateRow).toHaveBeenCalledTimes(2))
    expect(datasetsApi.updateRow).toHaveBeenNthCalledWith(1, 'ws', 'd1', 'r1', {
      cells: { name: 'Alicia' },
    })
    expect(datasetsApi.updateRow).toHaveBeenNthCalledWith(2, 'ws', 'd1', 'r1', {
      cells: { age: '31' },
    })
  })

  // Régression : cellules non contrôlées (`defaultValue`) — après un refetch
  // (retypage de colonne, édition concurrente) l'affichage restait figé sur la
  // valeur du montage tant que la ligne n'était pas remontée.
  it('reflète les valeurs serveur après un refetch', async () => {
    const { qc } = renderGrid(true)
    await waitFor(() => expect(cell('dataset-cell-name-r1').value).toBe('Alice'))

    vi.mocked(datasetsApi.getDataset).mockResolvedValue({
      ...detail,
      rows: [
        { id: 'r1', cells: { name: 'Alicia', age: '30' } },
        { id: 'r2', cells: { name: 'Bob', age: '25' } },
      ],
    })
    await act(async () => {
      await qc.invalidateQueries({ queryKey: ['dataset', 'ws', 'd1'] })
    })

    await waitFor(() => expect(cell('dataset-cell-name-r1').value).toBe('Alicia'))
  })

  // Corollaire : une saisie en cours (cellule focalisée) n'est pas écrasée par un
  // refetch d'arrière-plan — même garde que les champs de propriété.
  it('ne réinitialise pas une cellule en cours de saisie lors d’un refetch', async () => {
    const { qc } = renderGrid(true)
    await waitFor(() => expect(cell('dataset-cell-name-r1').value).toBe('Alice'))

    const name = cell('dataset-cell-name-r1')
    fireEvent.focus(name)
    fireEvent.change(name, { target: { value: 'saisie en cours' } })

    vi.mocked(datasetsApi.getDataset).mockResolvedValue({
      ...detail,
      rows: [
        { id: 'r1', cells: { name: 'Autre', age: '30' } },
        { id: 'r2', cells: { name: 'Bob', age: '25' } },
      ],
    })
    await act(async () => {
      await qc.invalidateQueries({ queryKey: ['dataset', 'ws', 'd1'] })
    })

    expect(cell('dataset-cell-name-r1').value).toBe('saisie en cours')
  })
})

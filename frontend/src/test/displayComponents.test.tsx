import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '../lib/i18n'
import { TimelineView } from '../components/TimelineBlock'
import { ChartView } from '../components/ChartBlock'
import { WorkspaceProvider } from '../contexts/WorkspaceContext'
import { datasetsApi } from '../lib/datasetsApi'

vi.mock('../lib/datasetsApi', () => ({
  datasetsApi: { getDataset: vi.fn() },
}))

describe('TimelineView', () => {
  it('rend les étapes numérotées avec le label par défaut', () => {
    render(
      <TimelineView attrs=' title="Plan"' body={'Un | Premier pas.\nDeux | Second pas.'} source="s" />,
    )
    expect(screen.getByTestId('timeline')).toBeInTheDocument()
    expect(screen.getByText('Étape 1')).toBeInTheDocument()
    expect(screen.getByText('Étape 2')).toBeInTheDocument()
    expect(screen.getByText('Premier pas.')).toBeInTheDocument()
    expect(screen.queryByTestId('block-diagnostic')).not.toBeInTheDocument()
  })

  it('label personnalisé via l’attribut label', () => {
    render(<TimelineView attrs=' label="Phase"' body="Un | x" source="s" />)
    expect(screen.getByText('Phase 1')).toBeInTheDocument()
  })

  it('ligne malformée → badge « n ligne(s) ignorée(s) », le reste rendu', () => {
    render(<TimelineView attrs="" body={' | sans titre\nOk | bien'} source="s" />)
    expect(screen.getByText('Ok')).toBeInTheDocument()
    expect(screen.getByTestId('block-diagnostic')).toHaveTextContent('1 ligne ignorée')
  })
})

describe('ChartView', () => {
  it('donut : rend un SVG et la légende', () => {
    render(
      <ChartView attrs=' type="donut"' body={'A | 3\nB | 1'} source="s" />,
    )
    expect(document.querySelector('svg')).not.toBeNull()
    expect(screen.getByText(/A — 3/)).toBeInTheDocument()
  })

  it('percent hors somme (97) → badge de diagnostic', () => {
    render(
      <ChartView attrs=' type="pie" format="percent"' body={'A | 60\nB | 37'} source="s" />,
    )
    expect(screen.getByTestId('block-diagnostic')).toHaveTextContent('ne totalise pas 100')
  })

  it('percent à 100 ± 0,5 → pas de badge', () => {
    render(
      <ChartView attrs=' type="pie" format="percent"' body={'A | 60\nB | 40.2'} source="s" />,
    )
    expect(screen.queryByTestId('block-diagnostic')).not.toBeInTheDocument()
  })

  it('type inconnu → repli tabulaire + badge', () => {
    render(<ChartView attrs=' type="radar"' body={'A | 1'} source="s" />)
    expect(screen.getByTestId('chart-fallback-table')).toBeInTheDocument()
    expect(screen.getByTestId('block-diagnostic')).toHaveTextContent('radar')
  })

  it('valeur non numérique → ligne ignorée + badge, le reste rendu', () => {
    render(<ChartView attrs=' type="bar"' body={'A | douze\nB | 4'} source="s" />)
    expect(screen.getByTestId('block-diagnostic')).toHaveTextContent('1 ligne ignorée')
    expect(document.querySelector('svg')).not.toBeNull()
  })

  it('en-tête multi-séries : header="true" nomme les séries', () => {
    render(
      <ChartView
        attrs=' type="bar" header="true"'
        body={'Mois | Prévu | Réel\nJan | 10 | 12\nFév | 8 | 7'}
        source="s"
      />,
    )
    expect(screen.getByText('Prévu')).toBeInTheDocument()
    expect(screen.getByText('Réel')).toBeInTheDocument()
  })
})

describe('ChartView source=dataset', () => {
  const DS_ID = '11111111-2222-3333-4444-555555555555'
  const getDataset = vi.mocked(datasetsApi.getDataset)

  function renderWithProviders(attrs: string, body = '') {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={qc}>
        <WorkspaceProvider>
          <ChartView attrs={attrs} body={body} source="s" />
        </WorkspaceProvider>
      </QueryClientProvider>,
    )
  }

  beforeEach(() => {
    getDataset.mockReset()
    localStorage.setItem('ws_slug', 'ws-test')
  })

  it('dataset chargé → chart rendu depuis les colonnes numériques', async () => {
    getDataset.mockResolvedValue({
      id: DS_ID,
      slug: 'ventes',
      label: 'Ventes',
      columns: [
        { slug: 'mois', label: 'Mois', type: 'text', position: 0, required: true },
        { slug: 'total', label: 'Total', type: 'int', position: 1, required: false },
      ],
      rows: [
        { id: 'r1', cells: { mois: 'Jan', total: '10' } },
        { id: 'r2', cells: { mois: 'Fév', total: '12' } },
      ],
    } as never)
    renderWithProviders(` type="donut" source="dataset://${DS_ID}"`)
    expect(await screen.findByText(/Jan — 10/)).toBeInTheDocument()
    expect(getDataset).toHaveBeenCalledWith('ws-test', DS_ID)
  })

  it('forme spec 40 dataset:<uuid> acceptée', async () => {
    getDataset.mockResolvedValue({
      id: DS_ID, slug: 's', label: 'S',
      columns: [
        { slug: 'k', label: 'K', type: 'text', position: 0, required: true },
        { slug: 'v', label: 'V', type: 'float', position: 1, required: false },
      ],
      rows: [{ id: 'r1', cells: { k: 'A', v: '3,5' } }],
    } as never)
    renderWithProviders(` type="donut" source="dataset:${DS_ID}"`)
    expect(await screen.findByText(/A — 3.5/)).toBeInTheDocument()
  })

  it('dataset introuvable → badge + repli sur le corps', async () => {
    getDataset.mockRejectedValue(new Error('404'))
    renderWithProviders(` source="dataset://${DS_ID}"`, 'corps de secours')
    expect(await screen.findByTestId('block-diagnostic')).toHaveTextContent('introuvable')
    expect(screen.getByText('corps de secours')).toBeInTheDocument()
  })

  it('hors session (pas de workspace courant) → badge, aucun appel réseau', () => {
    localStorage.removeItem('ws_slug')
    renderWithProviders(` source="dataset://${DS_ID}"`)
    expect(screen.getByTestId('block-diagnostic')).toHaveTextContent('hors session')
    expect(getDataset).not.toHaveBeenCalled()
  })

  it('aucune colonne numérique → badge + repli tabulaire', async () => {
    getDataset.mockResolvedValue({
      id: DS_ID, slug: 's', label: 'S',
      columns: [
        { slug: 'a', label: 'A', type: 'text', position: 0, required: true },
        { slug: 'b', label: 'B', type: 'text', position: 1, required: false },
      ],
      rows: [{ id: 'r1', cells: { a: 'x', b: 'y' } }],
    } as never)
    renderWithProviders(` source="dataset://${DS_ID}"`)
    expect(await screen.findByTestId('chart-fallback-table')).toBeInTheDocument()
    expect(screen.getByTestId('block-diagnostic')).toHaveTextContent('numérique')
  })
})

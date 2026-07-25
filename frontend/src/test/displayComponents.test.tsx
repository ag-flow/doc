import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import '../lib/i18n'
import { TimelineView } from '../components/TimelineBlock'
import { ChartView } from '../components/ChartBlock'

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

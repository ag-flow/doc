import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '../lib/i18n'
import { HeaderFilterPopover, type FilterColumn } from '../components/HeaderFilterPopover'
import type { FilterClause } from '../lib/api'

function renderPopover(column: FilterColumn, clause: FilterClause | null = null) {
  const onChange = vi.fn()
  render(<HeaderFilterPopover column={column} clause={clause} onChange={onChange} />)
  return { onChange }
}

const restricted: FilterColumn = {
  slug: 'statut',
  label: 'Statut',
  type: 'restricted_list',
  allowedValues: [
    { slug: 'done', label: 'Terminé' },
    { slug: 'en_cours', label: 'En cours' },
  ],
}

const textCol: FilterColumn = { slug: 'nom', label: 'Nom', type: 'text', allowedValues: [] }
const intCol: FilterColumn = { slug: 'points', label: 'Points', type: 'int', allowedValues: [] }
const dateCol: FilterColumn = { slug: 'echeance', label: 'Échéance', type: 'date', allowedValues: [] }
const boolCol: FilterColumn = { slug: 'actif', label: 'Actif', type: 'bool', allowedValues: [] }

describe('HeaderFilterPopover', () => {
  beforeEach(() => vi.clearAllMocks())

  it('restricted_list: multi-selection produces an `in` clause', () => {
    const { onChange } = renderPopover(restricted)
    fireEvent.click(screen.getByTestId('filter-btn-statut'))
    fireEvent.click(screen.getByTestId('filter-opt-statut-done'))
    fireEvent.click(screen.getByTestId('filter-opt-statut-en_cours'))
    fireEvent.click(screen.getByTestId('filter-apply-statut'))
    expect(onChange).toHaveBeenCalledWith({ op: 'in', values: ['done', 'en_cours'] })
  })

  it('restricted_list: applying with no selection clears the filter', () => {
    const { onChange } = renderPopover(restricted, { prop: 'statut', op: 'in', values: ['done'] })
    fireEvent.click(screen.getByTestId('filter-btn-statut'))
    // Décoche la valeur pré-cochée puis applique.
    fireEvent.click(screen.getByTestId('filter-opt-statut-done'))
    fireEvent.click(screen.getByTestId('filter-apply-statut'))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('text: default operator is `contains` and a value produces a clause', () => {
    const { onChange } = renderPopover(textCol)
    fireEvent.click(screen.getByTestId('filter-btn-nom'))
    expect((screen.getByTestId('filter-op-nom') as HTMLSelectElement).value).toBe('contains')
    fireEvent.change(screen.getByTestId('filter-value-nom'), { target: { value: 'abc' } })
    fireEvent.click(screen.getByTestId('filter-apply-nom'))
    expect(onChange).toHaveBeenCalledWith({ op: 'contains', value: 'abc' })
  })

  it('int: `between` produces a values pair [min, max]', () => {
    const { onChange } = renderPopover(intCol)
    fireEvent.click(screen.getByTestId('filter-btn-points'))
    fireEvent.change(screen.getByTestId('filter-op-points'), { target: { value: 'between' } })
    fireEvent.change(screen.getByTestId('filter-value-points'), { target: { value: '2' } })
    fireEvent.change(screen.getByTestId('filter-value2-points'), { target: { value: '8' } })
    fireEvent.click(screen.getByTestId('filter-apply-points'))
    expect(onChange).toHaveBeenCalledWith({ op: 'between', values: ['2', '8'] })
  })

  it('int: `between` with a missing bound clears instead of sending a half clause', () => {
    const { onChange } = renderPopover(intCol)
    fireEvent.click(screen.getByTestId('filter-btn-points'))
    fireEvent.change(screen.getByTestId('filter-op-points'), { target: { value: 'between' } })
    fireEvent.change(screen.getByTestId('filter-value-points'), { target: { value: '2' } })
    fireEvent.click(screen.getByTestId('filter-apply-points'))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('date: `after` produces a single-value clause', () => {
    const { onChange } = renderPopover(dateCol)
    fireEvent.click(screen.getByTestId('filter-btn-echeance'))
    fireEvent.change(screen.getByTestId('filter-op-echeance'), { target: { value: 'after' } })
    fireEvent.change(screen.getByTestId('filter-value-echeance'), { target: { value: '2026-01-01' } })
    fireEvent.click(screen.getByTestId('filter-apply-echeance'))
    expect(onChange).toHaveBeenCalledWith({ op: 'after', value: '2026-01-01' })
  })

  it('bool: selecting a value produces an `eq` clause', () => {
    const { onChange } = renderPopover(boolCol)
    fireEvent.click(screen.getByTestId('filter-btn-actif'))
    fireEvent.change(screen.getByTestId('filter-value-actif'), { target: { value: 'true' } })
    fireEvent.click(screen.getByTestId('filter-apply-actif'))
    expect(onChange).toHaveBeenCalledWith({ op: 'eq', value: 'true' })
  })

  it('bascule à droite (right-0) quand un popover à gauche déborderait du bord droit', () => {
    // Déclencheur près du bord droit : left(1180) + 224 > innerWidth(1280) - 8.
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      left: 1180, right: 1200, top: 0, bottom: 16, width: 20, height: 16, x: 1180, y: 0,
      toJSON: () => ({}),
    } as DOMRect)
    vi.stubGlobal('innerWidth', 1280)
    renderPopover(restricted)
    fireEvent.click(screen.getByTestId('filter-btn-statut'))
    const pop = screen.getByTestId('filter-popover-statut')
    expect(pop.className).toContain('right-0')
    expect(pop.className).not.toContain('left-0')
    vi.restoreAllMocks()
  })

  it('reste à gauche (left-0) quand il y a la place à droite', () => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      left: 300, right: 320, top: 0, bottom: 16, width: 20, height: 16, x: 300, y: 0,
      toJSON: () => ({}),
    } as DOMRect)
    vi.stubGlobal('innerWidth', 1280)
    renderPopover(textCol)
    fireEvent.click(screen.getByTestId('filter-btn-nom'))
    const pop = screen.getByTestId('filter-popover-nom')
    expect(pop.className).toContain('left-0')
    expect(pop.className).not.toContain('right-0')
    vi.restoreAllMocks()
  })

  it('the Clear button always emits null', () => {
    const { onChange } = renderPopover(textCol, { prop: 'nom', op: 'contains', value: 'abc' })
    fireEvent.click(screen.getByTestId('filter-btn-nom'))
    fireEvent.click(screen.getByTestId('filter-clear-nom'))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('shows an active state on the button when a clause is present', () => {
    renderPopover(restricted, { prop: 'statut', op: 'in', values: ['done'] })
    expect(screen.getByTestId('filter-btn-statut')).toHaveAttribute('data-active', 'true')
  })

  it('le panneau utilise .popover-panel (largeur fixe) et non .dialog (width:100%)', () => {
    // Anti-régression : `.dialog` (modale, width:100%) monté dans le conteneur
    // inline-block du déclencheur s'effondrait à la largeur de l'icône.
    renderPopover(textCol)
    fireEvent.click(screen.getByTestId('filter-btn-nom'))
    const pop = screen.getByTestId('filter-popover-nom')
    expect(pop.className).toContain('popover-panel')
    expect(pop.className.split(/\s+/)).not.toContain('dialog')
  })
})

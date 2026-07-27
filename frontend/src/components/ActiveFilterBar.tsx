import { useTranslation } from 'react-i18next'
import { X } from '@phosphor-icons/react'
import type { BlockQueryBody, FilterClause } from '../lib/api'
import { Button } from './ui/button'

interface Props {
  spec: Pick<BlockQueryBody, 'filters' | 'sort'>
  /** Libellé lisible d'une propriété (slug → label de colonne). */
  labelOf: (prop: string) => string
  /** Libellé d'une valeur de `restricted_list` (slug → label), sinon la valeur brute. */
  valueLabelOf: (prop: string, value: string) => string
  onRemoveFilter: (prop: string) => void
  onClearAll: () => void
  onSaveView: () => void
}

function clauseText(
  f: FilterClause,
  t: (k: string) => string,
  valueLabelOf: (prop: string, v: string) => string,
): string {
  const values = (f.values ?? (f.value != null ? [f.value] : [])).map((v) => valueLabelOf(f.prop, v))
  const op = t(`documents.filter.op.${f.op}`)
  if (f.op === 'in') return values.join(', ')
  if (f.op === 'between') return `${op} ${values[0]} – ${values[1]}`
  return `${op} ${values[0]}`
}

/** Barre des filtres actifs : une chip par filtre, supprimable, au-dessus de la
 *  table. Rien ne s'affiche quand aucun filtre n'est posé — la barre n'est pas
 *  un bandeau permanent. */
export function ActiveFilterBar({
  spec, labelOf, valueLabelOf, onRemoveFilter, onClearAll, onSaveView,
}: Props) {
  const { t } = useTranslation()
  if (spec.filters.length === 0) return null

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2" data-testid="active-filters">
      {spec.filters.map((f) => (
        <span key={f.prop} className="tag tag-accent gap-1.5" data-testid={`filter-chip-${f.prop}`}>
          <span className="font-[600]">{labelOf(f.prop)}</span>
          {clauseText(f, t, valueLabelOf)}
          <button
            type="button"
            onClick={() => onRemoveFilter(f.prop)}
            aria-label={`${t('documents.filter.clear')} ${labelOf(f.prop)}`}
            data-testid={`filter-chip-remove-${f.prop}`}
            className="ml-0.5 border-0 bg-transparent p-0 text-inherit"
          >
            <X size={11} weight="bold" />
          </button>
        </span>
      ))}
      <Button variant="ghost" size="sm" onClick={onClearAll} data-testid="clear-all-filters">
        {t('documents.clearAll')}
      </Button>
      <Button variant="ghost" size="sm" onClick={onSaveView} data-testid="save-view-btn">
        {t('views.saveAs')}
      </Button>
    </div>
  )
}

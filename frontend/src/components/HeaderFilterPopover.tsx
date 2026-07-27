import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Funnel } from '@phosphor-icons/react'
import type { FilterClause, QueryOperator } from '../lib/api'
import { Button } from './ui/button'

/** Opérateurs proposés par type de propriété — miroir strict de `OPS_BY_TYPE`
 *  (backend `schemas/query.py`). L'ordre place l'opérateur par défaut en tête. */
const OPS_BY_TYPE: Record<string, QueryOperator[]> = {
  text: ['contains', 'eq', 'starts_with'],
  url: ['contains', 'eq', 'starts_with'],
  int: ['eq', 'lt', 'gt', 'between'],
  float: ['eq', 'lt', 'gt', 'between'],
  date: ['eq', 'before', 'after', 'between'],
  restricted_list: ['in'],
  bool: ['eq'],
  reference: ['eq'],
}

export interface FilterColumn {
  slug: string
  label: string
  type: string
  allowedValues: { slug: string; label: string }[]
}

/** Clause sans le champ `prop` (la colonne le porte déjà) — ce que consomme
 *  `setFilter(prop, clause)` du hook QuerySpec. */
type ClausePatch = Omit<FilterClause, 'prop'>

interface Props {
  column: FilterColumn
  clause: FilterClause | null
  onChange: (clause: ClausePatch | null) => void
}

/** Type d'input HTML pour la saisie d'une valeur selon le type de propriété. */
function inputType(propType: string): 'number' | 'date' | 'text' {
  if (propType === 'int' || propType === 'float') return 'number'
  if (propType === 'date') return 'date'
  return 'text'
}

export function HeaderFilterPopover({ column, clause, onChange }: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLSpanElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  const ops = OPS_BY_TYPE[column.type] ?? ['eq']
  const active = clause !== null

  // Brouillon local, hydraté depuis la clause courante à chaque ouverture.
  const [op, setOp] = useState<QueryOperator>(clause?.op ?? ops[0])
  const [v1, setV1] = useState<string>(clause?.value ?? clause?.values?.[0] ?? '')
  const [v2, setV2] = useState<string>(clause?.values?.[1] ?? '')
  const [selected, setSelected] = useState<string[]>(
    clause?.values ?? (clause?.value ? [clause.value] : []),
  )

  /** Ferme et rend le focus au déclencheur : sans ça, Échap laisse le focus dans
   *  le vide et la navigation clavier repart du début du document. */
  function close() {
    setOpen(false)
    triggerRef.current?.focus()
  }

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
    }
  }, [open])

  function openPopover() {
    // Rehydrate le brouillon depuis l'état courant avant d'afficher.
    setOp(clause?.op ?? ops[0])
    setV1(clause?.value ?? clause?.values?.[0] ?? '')
    setV2(clause?.values?.[1] ?? '')
    setSelected(clause?.values ?? (clause?.value ? [clause.value] : []))
    setOpen(true)
  }

  function apply() {
    if (column.type === 'restricted_list') {
      onChange(selected.length > 0 ? { op: 'in', values: selected } : null)
    } else if (op === 'between') {
      onChange(v1 !== '' && v2 !== '' ? { op: 'between', values: [v1, v2] } : null)
    } else {
      onChange(v1 !== '' ? { op, value: v1 } : null)
    }
    close()
  }

  function clear() {
    onChange(null)
    close()
  }

  function toggleValue(slug: string) {
    setSelected((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug],
    )
  }

  return (
    <span className="relative inline-block" ref={rootRef} onClick={(e) => e.stopPropagation()}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => (open ? close() : openPopover())}
        className={active ? 'text-accent' : 'text-ink/[0.3] hover:text-ink/[0.6]'}
        title={t('documents.filter.title')}
        aria-expanded={open}
        data-testid={`filter-btn-${column.slug}`}
        data-active={active ? 'true' : 'false'}
      >
        <Funnel size={13} weight={active ? 'fill' : 'duotone'} />
      </button>

      {open && (
        <div
          className="dialog elev-lg absolute left-0 z-20 mt-1 w-56 gap-2 p-3 text-left"
          data-testid={`filter-popover-${column.slug}`}
        >
          {column.type === 'restricted_list' ? (
            <div className="dialog-scroll max-h-48 space-y-1 overflow-y-auto">
              {column.allowedValues.map((av) => (
                <label key={av.slug} className="flex items-center gap-2 text-[14px]">
                  <input
                    type="checkbox"
                    checked={selected.includes(av.slug)}
                    onChange={() => toggleValue(av.slug)}
                    data-testid={`filter-opt-${column.slug}-${av.slug}`}
                  />
                  {av.label}
                </label>
              ))}
            </div>
          ) : column.type === 'bool' ? (
            <select
              className="input"
              value={v1}
              onChange={(e) => setV1(e.target.value)}
              data-testid={`filter-value-${column.slug}`}
            >
              <option value="">—</option>
              <option value="true">{t('documents.filter.true')}</option>
              <option value="false">{t('documents.filter.false')}</option>
            </select>
          ) : (
            <>
              {ops.length > 1 && (
                <select
                  className="input"
                  value={op}
                  onChange={(e) => setOp(e.target.value as QueryOperator)}
                  data-testid={`filter-op-${column.slug}`}
                >
                  {ops.map((o) => (
                    <option key={o} value={o}>{t(`documents.filter.op.${o}`)}</option>
                  ))}
                </select>
              )}
              <input
                type={inputType(column.type)}
                className="input"
                placeholder={op === 'between' ? t('documents.filter.min') : t('documents.filter.value')}
                value={v1}
                onChange={(e) => setV1(e.target.value)}
                autoFocus
                data-testid={`filter-value-${column.slug}`}
              />
              {op === 'between' && (
                <input
                  type={inputType(column.type)}
                  className="input"
                  placeholder={t('documents.filter.max')}
                  value={v2}
                  onChange={(e) => setV2(e.target.value)}
                  data-testid={`filter-value2-${column.slug}`}
                />
              )}
            </>
          )}

          <div className="flex justify-between gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={clear}
              data-testid={`filter-clear-${column.slug}`}
            >
              {t('documents.filter.clear')}
            </Button>
            <Button size="sm" onClick={apply} data-testid={`filter-apply-${column.slug}`}>
              {t('documents.filter.apply')}
            </Button>
          </div>
        </div>
      )}
    </span>
  )
}

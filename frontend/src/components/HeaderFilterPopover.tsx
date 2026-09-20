import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Funnel } from '@phosphor-icons/react'
import type { FilterClause, QueryOperator } from '../lib/api'
import { Button } from './ui/button'

/** Largeur du panneau — doit rester le miroir de `.popover-panel` (components.css). */
const PANEL_WIDTH = 224
/** Marge minimale conservée avec les bords de la fenêtre. */
const VIEWPORT_MARGIN = 8

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
  // Position ABSOLUE à l'écran, calculée depuis le déclencheur. Le panneau est
  // sorti du tableau par un portail (voir plus bas) : il n'a plus d'ancêtre
  // positionné, donc il se place lui-même.
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const rootRef = useRef<HTMLSpanElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

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

  /** Place le panneau sous le déclencheur, en le rabattant dans la fenêtre.
   *
   *  Bascule au-dessus quand le bas manque de place : c'est le cas des dernières
   *  lignes d'une longue liste, où un panneau ouvert vers le bas sortait de
   *  l'écran. La largeur étant fixe, l'alignement horizontal se règle de même
   *  pour les colonnes de droite (STATUT, SÉVÉRITÉ…). */
  const place = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const height = panelRef.current?.offsetHeight ?? 0

    let left = rect.left
    if (left + PANEL_WIDTH > window.innerWidth - VIEWPORT_MARGIN) left = rect.right - PANEL_WIDTH
    left = Math.max(VIEWPORT_MARGIN, left)

    let top = rect.bottom + 4
    if (height > 0 && top + height > window.innerHeight - VIEWPORT_MARGIN) {
      top = Math.max(VIEWPORT_MARGIN, rect.top - 4 - height)
    }
    setPos({ top, left })
  }, [])

  // Mesure AVANT peinture : le panneau doit apparaître directement au bon
  // endroit, sans saut visible. Sa hauteur n'est connue qu'une fois monté, d'où
  // le placement en deux temps (rendu hors écran, puis positionné).
  useLayoutEffect(() => {
    if (open) place()
  }, [open, place, op, selected.length])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    const onClick = (e: MouseEvent) => {
      const target = e.target as Node
      // Le panneau vit dans un portail : il n'est PAS dans `rootRef`. L'oublier
      // refermerait le popover au premier clic sur une case à cocher.
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return
      setOpen(false)
    }
    // Capture : le tableau a ses propres conteneurs défilants, dont le
    // défilement ne remonte pas jusqu'à `window` en phase de bouillonnement.
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, place])

  function openPopover() {
    setPos(null)
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

      {/* Sorti du tableau par un portail : le conteneur de défilement horizontal
          de la liste rogne tout ce qui dépasse, et le panneau s'y retrouvait
          coupé net sous la dernière ligne — boutons Effacer/Appliquer inclus.
          Aucun `overflow` d'ancêtre ne peut atteindre `document.body`. */}
      {open && createPortal(
        <div
          ref={panelRef}
          className="popover-panel elev-lg fixed z-50 text-left"
          style={{
            top: pos?.top ?? 0,
            left: pos?.left ?? 0,
            // Tant que la hauteur n'est pas mesurée, le panneau est rendu mais
            // invisible : on ne montre jamais une position provisoire.
            visibility: pos ? 'visible' : 'hidden',
          }}
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
        </div>,
        document.body,
      )}
    </span>
  )
}

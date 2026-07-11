import { useCallback, useMemo, useState } from 'react'
import type { BlockQueryBody, FilterClause, SortKey } from '../lib/api'

export type WindowMode = 'browse' | 'query'

const DEFAULT_PAGE_SIZE = 100

function emptySpec(pageSize: number): BlockQueryBody {
  return { filters: [], sort: [], projection: null, page: 1, page_size: pageSize }
}

export interface UseQuerySpecStateResult {
  /** `QuerySpec` front unique (structure du corps REST, rejouable par une requête nommée). */
  spec: BlockQueryBody
  /** Dérivé de `spec` : aucun filtre/tri actif → 'browse' (arbre) ; sinon → 'query' (plat paginé). */
  mode: WindowMode
  /** Pose ou retire (clause=null) le filtre d'une propriété. Repart en page 1. */
  setFilter: (prop: string, clause: Omit<FilterClause, 'prop'> | null) => void
  /** Cycle asc → desc → aucun sur une clé de tri. Repart en page 1.
   *  `additive` (Maj-clic) : conserve les autres clés et compose un tri multi-clé
   *  (la clé est ajoutée/retirée en fin de liste) ; sinon remplace le tri courant. */
  toggleSort: (key: string, additive?: boolean) => void
  setPage: (page: number) => void
  /** Hydrate l'état depuis un `QuerySpec` externe (ex. requête nommée). */
  loadSpec: (next: BlockQueryBody) => void
  /** Revient au mode browse (vide filtres/tri/projection, conserve page_size). */
  reset: () => void
}

export function useQuerySpecState(pageSize = DEFAULT_PAGE_SIZE): UseQuerySpecStateResult {
  const [spec, setSpec] = useState<BlockQueryBody>(() => emptySpec(pageSize))

  const mode: WindowMode = useMemo(
    () => (spec.filters.length > 0 || spec.sort.length > 0 ? 'query' : 'browse'),
    [spec.filters, spec.sort],
  )

  const setFilter = useCallback((prop: string, clause: Omit<FilterClause, 'prop'> | null) => {
    setSpec((prev) => {
      const filters = prev.filters.filter((f) => f.prop !== prop)
      if (clause) filters.push({ prop, ...clause })
      return { ...prev, filters, page: 1 }
    })
  }, [])

  const toggleSort = useCallback((key: string, additive = false) => {
    setSpec((prev) => {
      const existing = prev.sort.find((s) => s.key === key)
      // Cycle d'une clé : absente → asc, asc → desc, desc → retirée (null).
      const next: SortKey | null =
        existing === undefined
          ? { key, dir: 'asc' }
          : existing.dir === 'asc'
            ? { key, dir: 'desc' }
            : null
      const others = prev.sort.filter((s) => s.key !== key)
      // Maj-clic : compose avec les autres clés (ordre = précédence) ;
      // clic simple : remplace tout le tri par cette seule clé.
      const base = additive ? others : []
      const sort: SortKey[] = next ? [...base, next] : base
      return { ...prev, sort, page: 1 }
    })
  }, [])

  const setPage = useCallback((page: number) => {
    setSpec((prev) => ({ ...prev, page }))
  }, [])

  const loadSpec = useCallback((next: BlockQueryBody) => {
    setSpec(next)
  }, [])

  const reset = useCallback(() => {
    setSpec((prev) => emptySpec(prev.page_size))
  }, [])

  return { spec, mode, setFilter, toggleSort, setPage, loadSpec, reset }
}

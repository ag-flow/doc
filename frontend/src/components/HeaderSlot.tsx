import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'

/**
 * Slot d'actions de l'en-tête : une page peut monter ses actions contextuelles
 * (Éditer, Enregistrer, indicateur d'état…) sur la ligne du fil d'Ariane, à
 * droite — comme la maquette. Quand un slot est occupé, l'en-tête efface son
 * bouton « Rechercher » (Cmd/Ctrl+K reste actif) : une seule rangée d'actions.
 */

interface SlotCtxValue {
  /** Élément DOM cible (le span de l'en-tête), publié par AppHeader. */
  el: HTMLElement | null
  setEl: (el: HTMLElement | null) => void
  /** Nombre de HeaderActions montés — l'en-tête s'y adapte. */
  active: number
  register: () => () => void
}

const SlotCtx = createContext<SlotCtxValue | null>(null)

export function HeaderSlotProvider({ children }: { children: ReactNode }) {
  const [el, setEl] = useState<HTMLElement | null>(null)
  const [active, setActive] = useState(0)
  const register = useCallback(() => {
    setActive((n) => n + 1)
    return () => setActive((n) => Math.max(0, n - 1))
  }, [])
  const value = useMemo(() => ({ el, setEl, active, register }), [el, active, register])
  return <SlotCtx.Provider value={value}>{children}</SlotCtx.Provider>
}

/** Côté AppHeader : publie la cible et sait si un slot est occupé. */
export function useHeaderSlot(): { setEl: (el: HTMLElement | null) => void; occupied: boolean } {
  const ctx = useContext(SlotCtx)
  return { setEl: ctx?.setEl ?? (() => {}), occupied: (ctx?.active ?? 0) > 0 }
}

/** Côté page : monte ses enfants dans l'en-tête. Hors layout (tests, page
 *  isolée), les enfants se rendent sur place — aucun bouton ne disparaît. */
export function HeaderActions({ children }: { children: ReactNode }) {
  const ctx = useContext(SlotCtx)
  const register = ctx?.register
  useEffect(() => (register ? register() : undefined), [register])
  if (!ctx?.el) return <>{children}</>
  return createPortal(children, ctx.el)
}

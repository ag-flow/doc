/**
 * Service headless de sélection d'un document cible (épic MLD — F4c).
 *
 * Porte la logique « chercher un document et en choisir un » indépendamment de
 * toute surface d'affichage : ni BlockNote, ni la modale `LinkSearchPopup` n'en
 * font partie. Un appelant fournit le workspace et ce qu'il veut faire du
 * document choisi ; il reçoit l'état et les gestes clavier à brancher sur son
 * propre rendu.
 *
 * Extrait de `LinkSearchPopup` (qui en reste le premier consommateur) pour que
 * d'autres surfaces — le canvas de modèle de données (F7) notamment — puissent
 * lier un document sans dépendre de l'éditeur markdown.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { referencesApi, type DocumentSearchResult } from '../lib/api'

/** Fenêtre de silence avant d'interroger le serveur (ms). */
export const SEARCH_DEBOUNCE_MS = 200

export interface UseDocumentPickerOptions {
  /** Workspace dans lequel chercher. */
  wsSlug: string
  /** Appelé avec le document retenu (clic ou touche Entrée). */
  onSelect: (doc: DocumentSearchResult) => void
  /** Appelé sur Échap. */
  onClose: () => void
}

export interface UseDocumentPickerResult {
  query: string
  setQuery: (q: string) => void
  results: DocumentSearchResult[]
  loading: boolean
  /** Index surligné dans `results`. */
  selected: number
  setSelected: (i: number) => void
  /** Navigation clavier : ↑ ↓ pour parcourir, Entrée pour choisir, Échap pour fermer. */
  handleKey: (e: KeyboardEvent) => void
}

export function useDocumentPicker({
  wsSlug,
  onSelect,
  onClose,
}: UseDocumentPickerOptions): UseDocumentPickerResult {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<DocumentSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(0)

  // Les callbacks sont lus au moment de l'événement : un appelant qui passe une
  // lambda inline ne doit pas réarmer la recherche à chaque rendu.
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      setLoading(false)
      return
    }
    setLoading(true)
    // `cancelled` ET `clearTimeout` : la frappe suivante annule la requête en
    // vol, sinon une réponse lente écraserait une réponse plus récente.
    let cancelled = false
    const timer = setTimeout(() => {
      referencesApi
        .searchDocuments(wsSlug, query)
        .then((r) => {
          if (cancelled) return
          setResults(r)
          setSelected(0)
        })
        // Une recherche qui échoue ne casse pas la saisie : liste vide.
        .catch(() => {
          if (!cancelled) setResults([])
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }, SEARCH_DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, wsSlug])

  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCloseRef.current()
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelected((s) => Math.min(s + 1, results.length - 1))
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelected((s) => Math.max(s - 1, 0))
      }
      if (e.key === 'Enter' && results[selected]) {
        e.preventDefault()
        onSelectRef.current(results[selected])
      }
    },
    [results, selected],
  )

  return { query, setQuery, results, loading, selected, setSelected, handleKey }
}

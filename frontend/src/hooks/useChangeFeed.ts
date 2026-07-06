import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { changesApi, type ChangeEntityKind, type ChangeFeedOut } from '../lib/api'

const POLL_INTERVAL_MS = 5_000

/** Query keys (préfixes) à invalider quand une entité d'un kind donné évolue. */
function keysForKind(kind: ChangeEntityKind, ws: string): unknown[][] {
  switch (kind) {
    case 'document':
      return [
        ['documents', ws],
        ['ws-documents', ws],
        ['block-documents', ws],
        ['document', ws],
        ['doc-values', ws],
        ['block-values', ws],
        ['backlinks', ws],
        ['broken-links', ws],
      ]
    case 'type':
      return [
        ['types', ws],
        ['types-rich', ws],
        ['allowed-types', ws],
      ]
    case 'property':
      return [
        ['types-rich', ws],
        ['doc-values', ws],
        ['block-values', ws],
      ]
    case 'block':
      return [
        ['blocs', ws],
        ['blocks', ws],
        ['block-documents', ws],
        ['allowed-types', ws],
      ]
    case 'template':
      // Import de template : le modèle entier a pu bouger.
      return [
        ['types', ws],
        ['types-rich', ws],
        ['allowed-types', ws],
        ['blocs', ws],
        ['blocks', ws],
        ['templates'],
      ]
  }
}

/**
 * Suit le change feed du workspace et invalide les caches TanStack Query
 * quand d'autres sessions (UI, MCP, automates) modifient le contenu ou le
 * modèle — la page affichée se rafraîchit sans rechargement complet.
 *
 * Le premier fetch établit seulement le curseur (pas d'invalidation : les
 * données viennent d'être chargées). Le polling est suspendu quand l'onglet
 * est caché (comportement par défaut de refetchInterval).
 */
export function useChangeFeed(ws: string | undefined): void {
  const queryClient = useQueryClient()
  const cursorRef = useRef<number | null>(null)
  const wsRef = useRef<string | undefined>(ws)

  // Changement de workspace → repartir d'un curseur vierge
  if (wsRef.current !== ws) {
    wsRef.current = ws
    cursorRef.current = null
  }

  const { data } = useQuery<ChangeFeedOut>({
    queryKey: ['change-feed', ws],
    queryFn: () => changesApi.get(ws!, cursorRef.current ?? 0),
    enabled: Boolean(ws),
    refetchInterval: POLL_INTERVAL_MS,
    // Le feed lui-même ne doit jamais être servi depuis le cache
    staleTime: 0,
    gcTime: 0,
  })

  useEffect(() => {
    if (!data || !ws) return
    if (cursorRef.current === null) {
      // Baseline : on prend le curseur courant sans invalider.
      cursorRef.current = data.next_cursor
      return
    }
    if (data.next_cursor === cursorRef.current && !data.has_more) return
    cursorRef.current = data.next_cursor
    const kinds = new Set<ChangeEntityKind>(data.changes.map((c) => c.entity_kind))
    for (const kind of kinds) {
      for (const key of keysForKind(kind, ws)) {
        void queryClient.invalidateQueries({ queryKey: key })
      }
    }
  }, [data, ws, queryClient])
}

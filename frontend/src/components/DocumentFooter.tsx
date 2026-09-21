/**
 * Pied de l'écran document : enfants, réactions, commentaires (épic MLD — F4e).
 *
 * Ce bloc était **écrit deux fois**, à l'identique, dans `DocumentReader` et
 * `DocumentEditor` — chacun avec sa propre requête de réactions et sa propre
 * mutation. C'est le symptôme que F4e attaque : une évolution faite d'un côté et
 * oubliée de l'autre. Ici les deux copies n'avaient pas encore divergé ; il
 * s'agit de les réunir avant que ça n'arrive.
 *
 * La requête de réactions vit désormais dans ce composant, donc en un seul
 * endroit quel que soit le mode.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { reactionsApi, type ReactionOut } from '../lib/api'
import { DocumentChildrenPanel } from './DocumentChildrenPanel'
import { ReactionBar } from './ReactionBar'
import { CommentsPanel } from './CommentsPanel'

interface Props {
  ws: string
  blocSlug: string
  docId: string
}

export function DocumentFooter({ ws, blocSlug, docId }: Props) {
  const queryClient = useQueryClient()

  const { data: reactions } = useQuery<ReactionOut>({
    queryKey: ['doc-reactions', ws, docId],
    queryFn: () => reactionsApi.getDocReactions(ws, docId),
    staleTime: 30_000,
  })

  const reactDocMutation = useMutation({
    mutationFn: (nature: 1 | -1) => reactionsApi.toggleDocReaction(ws, docId, nature),
    onSuccess: (updated: ReactionOut) => {
      queryClient.setQueryData(['doc-reactions', ws, docId], updated)
    },
  })

  return (
    <div data-testid="document-footer">
      <div className="mt-8">
        <DocumentChildrenPanel ws={ws} blocSlug={blocSlug} docId={docId} />
      </div>
      <div className="mt-6 border-t border-[var(--color-divider)] pt-6">
        {reactions && (
          <div className="mb-4">
            <ReactionBar
              reactions={reactions}
              onReact={(n) => reactDocMutation.mutate(n)}
              disabled={reactDocMutation.isPending}
            />
          </div>
        )}
        <CommentsPanel ws={ws} docId={docId} />
      </div>
    </div>
  )
}

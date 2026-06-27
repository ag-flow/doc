import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { reactionsApi, type CommentOut, type ReactionOut } from '../lib/api'
import { ReactionBar } from './ReactionBar'

interface CommentItemProps {
  ws: string
  docId: string
  comment: CommentOut
  onDelete: (id: string) => void
  deleting: boolean
}

function CommentItem({ ws, docId, comment, onDelete, deleting }: CommentItemProps) {
  const qc = useQueryClient()

  const reactMutation = useMutation({
    mutationFn: (nature: 1 | -1) =>
      reactionsApi.toggleCommentReaction(ws, docId, comment.id, nature),
    onSuccess: (updated: ReactionOut) => {
      qc.setQueryData<CommentOut[]>(['comments', ws, docId], (prev) =>
        prev?.map((c) => (c.id === comment.id ? { ...c, reactions: updated } : c))
      )
    },
  })

  const date = new Date(comment.created_at).toLocaleDateString('fr-FR', {
    day: 'numeric', month: 'short', year: 'numeric',
  })

  return (
    <div className="py-3 border-b border-gray-100 last:border-0">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium text-gray-800">{comment.author_label}</span>
            <span className="text-xs text-gray-400">{date}</span>
          </div>
          <p className="text-sm text-gray-700 whitespace-pre-wrap break-words">{comment.body}</p>
          <div className="mt-2">
            <ReactionBar
              reactions={comment.reactions}
              onReact={(n) => reactMutation.mutate(n)}
              disabled={reactMutation.isPending}
            />
          </div>
        </div>
        {comment.is_mine && (
          <button
            onClick={() => onDelete(comment.id)}
            disabled={deleting}
            className="shrink-0 text-gray-300 hover:text-red-500 transition-colors disabled:opacity-50"
            title="Supprimer"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </div>
  )
}

interface CommentsPanelProps {
  ws: string
  docId: string
}

export function CommentsPanel({ ws, docId }: CommentsPanelProps) {
  const [draft, setDraft] = useState('')
  const qc = useQueryClient()

  const { data: comments = [], isLoading } = useQuery<CommentOut[]>({
    queryKey: ['comments', ws, docId],
    queryFn: () => reactionsApi.getComments(ws, docId),
    staleTime: 30_000,
  })

  const addMutation = useMutation({
    mutationFn: () => reactionsApi.addComment(ws, docId, draft.trim()),
    onSuccess: (newComment: CommentOut) => {
      qc.setQueryData<CommentOut[]>(['comments', ws, docId], (prev) => [
        ...(prev ?? []),
        newComment,
      ])
      setDraft('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (commentId: string) => reactionsApi.deleteComment(ws, docId, commentId),
    onSuccess: (_: void, commentId: string) => {
      qc.setQueryData<CommentOut[]>(['comments', ws, docId], (prev) =>
        prev?.filter((c) => c.id !== commentId)
      )
    },
  })

  const canSubmit = draft.trim().length > 0 && !addMutation.isPending

  return (
    <div className="mt-6">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        Commentaires
        {comments.length > 0 && (
          <span className="ml-2 text-xs font-normal text-gray-400">({comments.length})</span>
        )}
      </h3>

      {isLoading ? (
        <p className="text-xs text-gray-400">Chargement…</p>
      ) : comments.length === 0 ? (
        <p className="text-xs text-gray-400 mb-3">Aucun commentaire.</p>
      ) : (
        <div className="mb-3">
          {comments.map((c) => (
            <CommentItem
              key={c.id}
              ws={ws}
              docId={docId}
              comment={c}
              onDelete={(id) => deleteMutation.mutate(id)}
              deleting={deleteMutation.isPending}
            />
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ajouter un commentaire…"
          rows={3}
          maxLength={2000}
          className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none
                     focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent
                     placeholder:text-gray-400"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && canSubmit) {
              e.preventDefault()
              addMutation.mutate()
            }
          }}
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">{draft.length}/2000 · Ctrl+Entrée pour envoyer</span>
          <button
            onClick={() => addMutation.mutate()}
            disabled={!canSubmit}
            className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg
                       hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Commenter
          </button>
        </div>
      </div>
    </div>
  )
}

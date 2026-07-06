import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Check, Eye, Pencil } from 'lucide-react'
import { reactionsApi, type DocumentOut, type ReactionOut } from '../lib/api'
import { MarkdownViewer } from './MarkdownViewer'
import { DocumentChildrenPanel } from './DocumentChildrenPanel'
import { BacklinksPanel } from './BacklinksPanel'
import { ReactionBar } from './ReactionBar'
import { CommentsPanel } from './CommentsPanel'

interface DocumentReaderProps {
  ws: string
  blocSlug: string
  docId: string
  doc: DocumentOut
  onEdit: () => void
}

/**
 * Vue lecture « wiki » d'un document : colonne centrée aérée, sans panneau
 * propriétés. Mode par défaut à l'ouverture ; l'édition se déclenche via `onEdit`.
 */
export function DocumentReader({ ws, blocSlug, docId, doc, onEdit }: DocumentReaderProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [copied, setCopied] = useState(false)

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

  const hasContent = Boolean(doc.content && doc.content.trim())

  return (
    <div className="p-6" data-testid="document-reader">
      <div className="mx-auto max-w-[900px]">
        <div className="mb-6 flex items-start gap-4">
          <h1 className="text-3xl font-bold leading-tight text-gray-900">{doc.title}</h1>
          <div className="ml-auto flex shrink-0 items-center gap-2 pt-1">
            {doc.exposed && (
              <button
                type="button"
                title="Copier le lien public"
                onClick={() => {
                  void navigator.clipboard.writeText(`${window.location.origin}/pub/${docId}`)
                  setCopied(true)
                  setTimeout(() => setCopied(false), 1500)
                }}
                className="flex items-center gap-1 rounded-md px-2 py-1.5 text-xs text-emerald-600
                  hover:bg-emerald-50 transition-colors"
              >
                {copied ? <Check size={13} /> : <Eye size={13} />}
              </button>
            )}
            <button
              type="button"
              onClick={onEdit}
              className="flex items-center gap-1.5 rounded-md bg-gray-100 px-3 py-1.5 text-xs
                font-medium text-gray-600 hover:bg-gray-200 transition-colors"
              data-testid="document-edit-btn"
            >
              <Pencil size={13} />
              {t('editor.edit')}
            </button>
          </div>
        </div>

        {doc.functional_type_slug && (
          <div className="mb-6 text-sm text-gray-400" data-testid="document-type-badge">
            {doc.functional_type_slug}
          </div>
        )}

        {hasContent ? (
          <MarkdownViewer content={doc.content ?? ''} bare />
        ) : (
          <p className="italic text-gray-400">{t('editor.readEmpty')}</p>
        )}

        <div className="mt-8">
          <DocumentChildrenPanel ws={ws} blocSlug={blocSlug} docId={docId} />
        </div>

        <div className="mt-8 border-t border-gray-100 pt-6">
          <BacklinksPanel ws={ws} docId={docId} blocSlug={blocSlug} />
        </div>

        <div className="mt-6 border-t border-gray-100 pt-6">
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
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Check, LinkSimple, PencilSimple } from '@phosphor-icons/react'
import { reactionsApi, type DocumentOut, type ReactionOut } from '../lib/api'
import { relativeDate } from '../lib/relativeDate'
import { MarkdownViewer } from './MarkdownViewer'
import { DocumentChildrenPanel } from './DocumentChildrenPanel'
import { BacklinksPanel } from './BacklinksPanel'
import { PropertiesPanel } from './PropertiesPanel'
import { ReactionBar } from './ReactionBar'
import { CommentsPanel } from './CommentsPanel'
import { DocumentShell } from './DocumentShell'
import { Button } from './ui/button'

interface DocumentReaderProps {
  ws: string
  blocSlug: string
  docId: string
  doc: DocumentOut
  onEdit: () => void
}

/**
 * Vue lecture d'un document. Elle partage l'ossature `DocumentShell` avec
 * l'édition : même feuille, mêmes marges, même mesure.
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
    <div data-testid="document-reader">
      <DocumentShell
        kicker={[doc.functional_type_slug, blocSlug].filter(Boolean).join(' · ')}
        title={
          <h1 className="m-0 max-w-[20ch] text-[42px] tracking-[-0.03em]">{doc.title}</h1>
        }
        meta={
          <>
            {doc.slug && (
              <span className="inline-flex items-center gap-1">
                <LinkSimple size={13} weight="duotone" />
                <span className="[font-family:var(--font-mono)]">{doc.slug}</span>
              </span>
            )}
            <span>
              v{doc.version} · {t('editor.modifiedAt', { when: relativeDate(doc.updated_at) })}
            </span>
            <span className="flex-1" />
            {doc.exposed && <span className="tag tag-accent">{t('documents.public')}</span>}
          </>
        }
        actions={
          <>
            {doc.exposed && (
              <Button
                variant="icon"
                size="sm"
                title={t('editor.copyPublicLink')}
                onClick={() => {
                  void navigator.clipboard.writeText(`${window.location.origin}/pub/${docId}`)
                  setCopied(true)
                  setTimeout(() => setCopied(false), 1500)
                }}
              >
                {copied ? <Check size={14} weight="bold" /> : <LinkSimple size={14} weight="duotone" />}
              </Button>
            )}
            <Button onClick={onEdit} data-testid="document-edit-btn">
              <PencilSimple size={14} weight="duotone" />
              {t('editor.edit')}
            </Button>
          </>
        }
        aside={
          <>
            <div className="doc-aside-kicker">{t('editor.properties')}</div>
            <PropertiesPanel ws={ws} docId={docId} functionalTypeSlug={doc.functional_type_slug} />
            <BacklinksPanel ws={ws} docId={docId} blocSlug={blocSlug} />
          </>
        }
        footer={
          <>
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
          </>
        }
      >
        {hasContent ? (
          <MarkdownViewer content={doc.content ?? ''} bare />
        ) : (
          <p className="text-muted italic">{t('editor.readEmpty')}</p>
        )}
      </DocumentShell>
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Check, Copy, FilePdf, LinkSimple, ListBullets, PencilSimple } from '@phosphor-icons/react'
import { reactionsApi, type DocumentOut, type ReactionOut } from '../lib/api'
import { relativeDate } from '../lib/relativeDate'
import { stripTitleHeading } from '../lib/markdownTitle'
import { MarkdownViewer } from './MarkdownViewer'
import { DocumentChildrenPanel } from './DocumentChildrenPanel'
import { BacklinksPanel } from './BacklinksPanel'
import { PropertiesPanel } from './PropertiesPanel'
import { ReactionBar } from './ReactionBar'
import { CommentsPanel } from './CommentsPanel'
import { DocumentShell } from './DocumentShell'
import { DocumentToc, DocumentPrevNext } from './DocumentTocNav'
import { ExportPdfDialog } from './ExportPdfDialog'
import { Button } from './ui/button'

const TOC_STORAGE_KEY = 'docflow.doc.toc'

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
  const [copiedDoc, setCopiedDoc] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  // Sommaire à gauche : ouvert par défaut, le choix est retenu localement.
  const [tocOpen, setTocOpen] = useState(() => localStorage.getItem(TOC_STORAGE_KEY) !== '0')
  function toggleToc() {
    setTocOpen((open) => {
      localStorage.setItem(TOC_STORAGE_KEY, open ? '0' : '1')
      return !open
    })
  }

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

  // Beaucoup de documents commencent par « # <titre> » (modèles de contenu) :
  // le shell affiche déjà ce titre, on retire le doublon EN LECTURE seulement
  // (le contenu en base n'est jamais modifié ; l'édition montre tout).
  const displayContent = stripTitleHeading(doc.content ?? '', doc.title)
  const hasContent = Boolean(displayContent.trim())

  return (
    <div data-testid="document-reader">
      <DocumentShell
        kicker={[doc.functional_type_slug, blocSlug].filter(Boolean).join(' · ')}
        title={
          <h1 className="m-0 text-[42px] leading-[1.08] tracking-[-0.03em]">{doc.title}</h1>
        }
        nav={tocOpen ? <DocumentToc ws={ws} bloc={blocSlug} docId={docId} /> : undefined}
        meta={
          <>
            <button
              type="button"
              onClick={toggleToc}
              title={t(tocOpen ? 'docnav.hideToc' : 'docnav.showToc')}
              aria-pressed={tocOpen}
              data-testid="toc-toggle"
              className={`inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 ${
                tocOpen ? 'text-accent-700' : 'text-ink/[0.5]'
              } hover:text-accent-700`}
            >
              <ListBullets size={14} weight="duotone" />
              {t('docnav.toc')}
            </button>
            {doc.slug && (
              <span className="inline-flex items-center gap-1">
                <LinkSimple size={13} weight="duotone" />
                <span className="[font-family:var(--font-mono)]">{doc.slug}</span>
              </span>
            )}
            <span>
              v{doc.version} · {t('editor.modifiedAt', { when: relativeDate(doc.updated_at) })}{doc.updated_by ? ` par ${doc.updated_by}` : ''}
            </span>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(doc.content ?? '')
                setCopiedDoc(true)
                setTimeout(() => setCopiedDoc(false), 1500)
              }}
              title={t('editor.copyDocument')}
              data-testid="copy-document-btn"
              className="inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-ink/[0.5] hover:text-accent-700"
            >
              {copiedDoc ? <Check size={14} weight="bold" /> : <Copy size={14} weight="duotone" />}
              {copiedDoc ? t('editor.copyDocumentDone') : t('editor.copyLabel')}
            </button>
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
            <Button
              variant="icon"
              size="sm"
              title={t('exportPdf.title')}
              onClick={() => setExportOpen(true)}
              data-testid="export-pdf-btn"
            >
              <FilePdf size={14} weight="duotone" />
            </Button>
            <Button onClick={onEdit} data-testid="document-edit-btn">
              <PencilSimple size={14} weight="duotone" />
              {t('editor.edit')}
            </Button>
          </>
        }
        aside={
          <>
            <PropertiesPanel
              ws={ws}
              docId={docId}
              functionalTypeSlug={doc.functional_type_slug}
              readOnly
            />
            <BacklinksPanel ws={ws} docId={docId} blocSlug={blocSlug} />
          </>
        }
        footer={
          <>
            <DocumentPrevNext ws={ws} bloc={blocSlug} docId={docId} />
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
          <MarkdownViewer content={displayContent} bare />
        ) : (
          <p className="text-muted italic">{t('editor.readEmpty')}</p>
        )}
      </DocumentShell>

      {exportOpen && (
        <ExportPdfDialog
          ws={ws}
          blocSlug={blocSlug}
          docId={docId}
          onClose={() => setExportOpen(false)}
        />
      )}
    </div>
  )
}

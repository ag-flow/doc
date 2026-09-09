import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  BookOpen,
  Check,
  Copy,
  FilePdf,
  Images,
  LinkSimple,
  ListBullets,
  Minus,
  PencilSimple,
  Plus,
  Sidebar,
  SpinnerGap,
  TextAa,
} from '@phosphor-icons/react'
import { useReadingPrefs } from '../hooks/useReadingPrefs'
import { reactionsApi, type DocumentOut, type ReactionOut } from '../lib/api'
import { relativeDate } from '../lib/relativeDate'
import { stripTitleHeading } from '../lib/markdownTitle'
import { MarkdownViewer, type MarkdownViewerHandle } from './MarkdownViewer'
import { DocumentChildrenPanel } from './DocumentChildrenPanel'
import { BacklinksPanel } from './BacklinksPanel'
import { PropertiesPanel } from './PropertiesPanel'
import { ReactionBar } from './ReactionBar'
import { CommentsPanel } from './CommentsPanel'
import { DocumentShell } from './DocumentShell'
import { DocumentToc, DocumentPrevNext } from './DocumentTocNav'
import { ExportPdfDialog } from './ExportPdfDialog'
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
  const [copiedDoc, setCopiedDoc] = useState(false)
  const [richState, setRichState] = useState<'idle' | 'busy' | 'done' | 'error'>('idle')
  const [exportOpen, setExportOpen] = useState(false)
  const viewerRef = useRef<MarkdownViewerHandle>(null)

  // Copie riche (texte + composants en images) : la rasterisation prend un
  // court instant, on montre un état d'attente puis un accusé.
  async function copyRich() {
    setRichState('busy')
    try {
      await viewerRef.current?.copyRich()
      setRichState('done')
      setTimeout(() => setRichState('idle'), 1500)
    } catch {
      setRichState('error')
      setTimeout(() => setRichState('idle'), 2500)
    }
  }
  // Préférences de lecture (sommaire, propriétés, échelle) : mémorisées par
  // compte via un magasin unique, retrouvées d'un document à l'autre.
  const {
    tocOpen,
    propsOpen,
    scale,
    readingMode,
    toggleToc,
    toggleProps,
    setReadingMode,
    incScale,
    decScale,
    resetScale,
    canInc,
    canDec,
  } = useReadingPrefs()

  // Raccourci « mode lecture » : replie/redéploie sommaire ET propriétés d'un
  // geste (⌘/Ctrl + \\, convention de bascule de panneaux latéraux). Ignoré
  // quand la frappe vise un champ de saisie (ex. panneau commentaires).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!(e.ctrlKey || e.metaKey) || e.key !== '\\') return
      const el = e.target as HTMLElement | null
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return
      e.preventDefault()
      setReadingMode(!readingMode)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [readingMode, setReadingMode])

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
            <button
              type="button"
              onClick={toggleProps}
              title={t(propsOpen ? 'docnav.hideProps' : 'docnav.showProps')}
              aria-pressed={propsOpen}
              data-testid="props-toggle"
              className={`inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 ${
                propsOpen ? 'text-accent-700' : 'text-ink/[0.5]'
              } hover:text-accent-700`}
            >
              <Sidebar size={14} weight="duotone" />
              {t('docnav.props')}
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
            <button
              type="button"
              onClick={() => void copyRich()}
              disabled={richState === 'busy'}
              title={t('editor.copyRichHint')}
              data-testid="copy-rich-btn"
              className="inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-ink/[0.5] hover:text-accent-700 disabled:cursor-wait"
            >
              {richState === 'busy' ? (
                <SpinnerGap size={14} weight="bold" className="animate-spin" />
              ) : richState === 'done' ? (
                <Check size={14} weight="bold" />
              ) : (
                <Images size={14} weight="duotone" />
              )}
              {richState === 'done'
                ? t('editor.copyRichDone')
                : richState === 'error'
                  ? t('editor.copyRichError')
                  : t('editor.copyRich')}
            </button>
            <span className="flex-1" />
            {doc.exposed && <span className="tag tag-accent">{t('documents.public')}</span>}
          </>
        }
        actions={
          <>
            <div className="flex items-center" data-testid="reading-scale" role="group" aria-label={t('reading.scale')}>
              <Button
                variant="icon"
                size="sm"
                title={t('reading.scaleDown')}
                aria-label={t('reading.scaleDown')}
                disabled={!canDec}
                onClick={decScale}
                data-testid="scale-down"
              >
                <Minus size={14} weight="bold" />
              </Button>
              <button
                type="button"
                onClick={resetScale}
                title={t('reading.scaleReset')}
                aria-label={t('reading.scaleValue', { pct: Math.round(scale * 100) })}
                data-testid="scale-reset"
                className="inline-flex min-w-[3.5ch] cursor-pointer items-center justify-center gap-1 border-0 bg-transparent px-0.5 text-[11px] tabular-nums text-ink/[0.6] hover:text-accent-700"
              >
                <TextAa size={13} weight="duotone" />
                {Math.round(scale * 100)}%
              </button>
              <Button
                variant="icon"
                size="sm"
                title={t('reading.scaleUp')}
                aria-label={t('reading.scaleUp')}
                disabled={!canInc}
                onClick={incScale}
                data-testid="scale-up"
              >
                <Plus size={14} weight="bold" />
              </Button>
            </div>
            <Button
              variant="icon"
              size="sm"
              title={t('reading.readingModeHint')}
              aria-label={t('reading.readingMode')}
              aria-pressed={readingMode}
              onClick={() => setReadingMode(!readingMode)}
              data-testid="reading-mode-toggle"
              className={readingMode ? 'text-accent-700' : undefined}
            >
              <BookOpen size={14} weight={readingMode ? 'fill' : 'duotone'} />
            </Button>
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
          propsOpen ? (
            <>
              <PropertiesPanel
                ws={ws}
                docId={docId}
                functionalTypeSlug={doc.functional_type_slug}
                readOnly
              />
              <BacklinksPanel ws={ws} docId={docId} blocSlug={blocSlug} />
            </>
          ) : undefined
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
          <MarkdownViewer ref={viewerRef} content={displayContent} bare />
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

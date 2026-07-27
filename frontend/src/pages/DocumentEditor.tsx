import { useCallback, useEffect, useRef, useState } from 'react'
import { useBlocker, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  ArrowsIn, ArrowsLeftRight, ArrowsOut, Check, Eye, EyeSlash, FloppyDisk,
  LinkSimple, Trash,
} from '@phosphor-icons/react'
import { ApiError, docsApi, reactionsApi, type DocumentOut, type ReactionOut } from '../lib/api'

const _SLUG_RE = /^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$/
import { Button } from '../components/ui/button'
import { ReparentDialog } from '../components/ReparentDialog'
import { Input } from '../components/ui/input'
import { PropertiesPanel } from '../components/PropertiesPanel'
import { ConflictResolver } from './ConflictResolver'
import { DocumentChildrenPanel } from '../components/DocumentChildrenPanel'
import { MarkdownEditor, type MarkdownEditorHandle } from '../components/MarkdownEditor'
import { ReactionBar } from '../components/ReactionBar'
import { CommentsPanel } from '../components/CommentsPanel'
import { BacklinksPanel } from '../components/BacklinksPanel'
import { DocumentReader } from '../components/DocumentReader'
import { DocumentShell } from '../components/DocumentShell'
import { relativeDate } from '../lib/relativeDate'

type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error'

interface ConflictData {
  baseVersion: number
  server: string
  serverVersion: number
  draft: string
}

export function DocumentEditor() {
  const { t } = useTranslation()
  const { wsSlug: ws, blocSlug, docId } = useParams<{ wsSlug: string; blocSlug: string; docId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const editorRef = useRef<MarkdownEditorHandle>(null)
  const expectedVersion = useRef<number>(0)
  const ancestorRef = useRef<{ title: string; content: string }>({ title: '', content: '' })
  // Identifiant du document actuellement chargé dans l'état local (titre / version).
  // Sert à distinguer un changement de document (resync obligatoire) d'un simple
  // refetch d'arrière-plan (resync gelée pendant l'édition — cf. FE-03).
  const loadedDocIdRef = useRef<string | null>(null)

  const [title, setTitle] = useState('')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [conflict, setConflict] = useState<ConflictData | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [copied, setCopied] = useState(false)
  // Lecture « wiki » par défaut à l'ouverture ; bascule vers l'éditeur à la demande.
  const [mode, setMode] = useState<'read' | 'edit'>('read')
  const [focusMode, setFocusMode] = useState(false)
  const [slugEdit, setSlugEdit] = useState(false)
  const [slugValue, setSlugValue] = useState<string>('')
  const [slugError, setSlugError] = useState<string | null>(null)
  // Incrémenté pour forcer le remontage de l'éditeur après résolution de conflit (FE-02),
  // afin de recharger le contenu fusionné à la place du brouillon pré-fusion.
  const [editorEpoch, setEditorEpoch] = useState(0)

  const exposeMutation = useMutation({
    mutationFn: (value: boolean) => docsApi.setDocumentExposed(ws!, docId!, value),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: ['document', ws, docId] })
      void queryClient.setQueryData(['document', ws, docId], updated)
    },
  })

  const [showReparent, setShowReparent] = useState(false)
  const { data: reactions } = useQuery<ReactionOut>({
    queryKey: ['doc-reactions', ws, docId],
    queryFn: () => reactionsApi.getDocReactions(ws!, docId!),
    enabled: Boolean(ws && docId),
    staleTime: 30_000,
  })

  const reactDocMutation = useMutation({
    mutationFn: (nature: 1 | -1) => reactionsApi.toggleDocReaction(ws!, docId!, nature),
    onSuccess: (updated: ReactionOut) => {
      queryClient.setQueryData(['doc-reactions', ws, docId], updated)
    },
  })

  const { data: doc, isLoading } = useQuery<DocumentOut>({
    queryKey: ['document', ws, docId],
    queryFn: () => docsApi.getDocument(ws!, docId!),
    enabled: Boolean(ws && docId),
  })

  const slugMutation = useMutation({
    mutationFn: (s: string | null) =>
      docsApi.patchDocument(ws!, docId!, { slug: s ?? undefined }),
    onSuccess: (updated) => {
      void queryClient.setQueryData(['document', ws, docId], updated)
      setSlugEdit(false)
      setSlugError(null)
    },
    onError: (err) => {
      setSlugError(err instanceof ApiError ? err.message : t('error.generic'))
    },
  })

  useEffect(() => {
    if (!doc) return
    const isNewDoc = loadedDocIdRef.current !== docId
    // FE-03 : ne pas resynchroniser titre / expectedVersion lors d'un refetch
    // d'arrière-plan (retour d'onglet, staleTime) pendant que l'utilisateur édite.
    // Réaligner expectedVersion sur la version serveur ici contournerait le verrou
    // optimiste et écraserait des modifications concurrentes sans dialogue de conflit ;
    // un titre en cours d'édition serait par ailleurs réinitialisé.
    if (!isNewDoc && status !== 'idle') return
    loadedDocIdRef.current = docId ?? null
    setTitle(doc.title)
    setSlugValue(doc.slug ?? '')
    expectedVersion.current = doc.version
    ancestorRef.current = { title: doc.title, content: doc.content ?? '' }
    // Changement de document : repartir d'un état propre (l'éditeur est remonté via key).
    if (isNewDoc) setStatus('idle')
  }, [doc, docId, status])

  const markDirty = useCallback(() => {
    setStatus((s) => (s === 'saving' ? s : 'dirty'))
  }, [])

  const doSave = useCallback(async (): Promise<boolean> => {
    if (!ws || !docId || !editorRef.current) return false
    if (status !== 'dirty' && status !== 'error') return true
    const content = await editorRef.current.getMarkdown()
    setStatus('saving')
    setErrorMsg(null)
    try {
      const updated = await docsApi.patchDocument(ws, docId, {
        title,
        content,
        expected_version: expectedVersion.current,
      })
      expectedVersion.current = updated.version
      ancestorRef.current = { title: updated.title, content: updated.content ?? '' }
      // Accusé discret (et non un toast bloquant) : « Enregistré » s'affiche à
      // la place de « non enregistré », puis s'efface de lui-même.
      setStatus('saved')
      void queryClient.invalidateQueries({ queryKey: ['document', ws, docId] })
      return true
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const serverDoc = (err.detail ?? {}) as Partial<DocumentOut>
        setConflict({
          baseVersion: expectedVersion.current,
          server: serverDoc.content ?? '',
          serverVersion: serverDoc.version ?? expectedVersion.current + 1,
          draft: content,
        })
        setStatus('idle')
      } else if (err instanceof ApiError && err.status === 422) {
        setStatus('error')
        setErrorMsg(err.message)
      } else {
        setStatus('error')
        setErrorMsg(err instanceof ApiError ? err.message : t('error.generic'))
      }
      return false
    }
  }, [ws, docId, title, status, queryClient, t])

  // L'accusé de sauvegarde retombe seul ; un nouveau `markDirty` le remplace.
  useEffect(() => {
    if (status !== 'saved') return
    const timer = setTimeout(() => setStatus((s) => (s === 'saved' ? 'idle' : s)), 2000)
    return () => clearTimeout(timer)
  }, [status])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        void doSave()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [doSave])

  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (status === 'dirty') e.preventDefault()
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [status])

  useEffect(() => {
    if (!focusMode) return
    function onEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') setFocusMode(false)
    }
    window.addEventListener('keydown', onEscape)
    return () => window.removeEventListener('keydown', onEscape)
  }, [focusMode])

  const blocker = useBlocker(status === 'dirty')

  const resolveConflict = useCallback(
    async (merged: string, serverVersion: number) => {
      const updated = await docsApi.patchDocument(ws!, docId!, {
        title,
        content: merged,
        expected_version: serverVersion,
      }).catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 409) {
          const newServer = (err.detail ?? {}) as Partial<DocumentOut>
          setConflict({
            baseVersion: serverVersion,
            server: newServer.content ?? '',
            serverVersion: newServer.version ?? serverVersion + 1,
            draft: merged,
          })
          throw new Error(`Conflit persistant — le document est désormais en v${newServer.version ?? '?'}`)
        }
        throw err
      })
      expectedVersion.current = updated.version
      ancestorRef.current = { title: updated.title, content: updated.content ?? '' }
      setStatus('idle')
      setConflict(null)
      // FE-02 : le brouillon pré-fusion est toujours affiché dans l'éditeur. On publie
      // synchroniquement le contenu fusionné (réponse serveur) dans le cache pour que
      // `initialContent` soit à jour, puis on force le remontage via editorEpoch. Sans
      // ça, la sauvegarde suivante renverrait le brouillon pré-fusion avec la bonne
      // expected_version et écraserait silencieusement les blocs serveur acceptés.
      queryClient.setQueryData(['document', ws, docId], updated)
      setEditorEpoch((e) => e + 1)
    },
    [ws, docId, title, queryClient],
  )

  async function deleteDocument() {
    if (!ws || !docId || !blocSlug) return
    setDeleting(true)
    try {
      await docsApi.deleteDocument(ws, docId)
      void queryClient.invalidateQueries({ queryKey: ['block-documents', ws, blocSlug] })
      void navigate(`/ws/${ws}/blocs/${blocSlug}/documents`)
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : t('error.generic'))
      setDeleting(false)
      setDeleteConfirm(false)
    }
  }

  if (isLoading) return <div className="p-8">{t('common.loading')}</div>
  if (!doc || !ws || !docId || !blocSlug) return <div className="p-8">{t('error.notFound')}</div>

  if (mode === 'read') {
    return (
      <DocumentReader
        ws={ws}
        blocSlug={blocSlug}
        docId={docId}
        doc={doc}
        onEdit={() => setMode('edit')}
      />
    )
  }

  // Bascule vers la lecture : si des modifications sont en attente, on enregistre
  // d'abord (l'éditeur va être démonté). En cas d'échec de sauvegarde, on reste en édition.
  const switchToRead = async () => {
    if (status === 'dirty' || status === 'error') {
      const ok = await doSave()
      if (!ok) return
    }
    setMode('read')
  }

  const statusNote =
    status === 'dirty' ? (
      <span className="inline-flex items-center gap-1.5 text-[12px] text-accent-2-700"
        data-testid="document-dirty">
        <span className="h-1.5 w-1.5 rounded-full bg-accent-2" />
        {t('editor.dirty')}
      </span>
    ) : status === 'saved' ? (
      <span className="inline-flex items-center gap-1.5 text-[12px] text-accent-700"
        data-testid="document-saved">
        <Check size={12} weight="bold" />
        {t('editor.savedAck')}
      </span>
    ) : status === 'error' ? (
      <span className="text-[12px] text-accent-2-700" data-testid="document-error">
        {errorMsg ?? t('error.generic')}
      </span>
    ) : null

  const actions = (
    <>
      {statusNote}
      <Button
        variant="icon"
        size="sm"
        title={doc.exposed ? t('blocs.makePrivate') : t('blocs.makePublic')}
        onClick={() => exposeMutation.mutate(!doc.exposed)}
        disabled={exposeMutation.isPending}
        data-testid="document-expose-btn"
      >
        {doc.exposed
          ? <Eye size={14} weight="duotone" />
          : <EyeSlash size={14} weight="duotone" />}
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
        onClick={() => void switchToRead()}
        title={t('editor.read')}
        data-testid="document-read-btn"
      >
        <Eye size={14} weight="duotone" />
      </Button>
      <Button
        variant="icon"
        size="sm"
        onClick={() => setFocusMode((f) => !f)}
        title={focusMode ? t('editor.focusExit') : t('editor.focusEnter')}
      >
        {focusMode ? <ArrowsIn size={14} weight="duotone" /> : <ArrowsOut size={14} weight="duotone" />}
      </Button>
      <Button
        variant="icon"
        size="sm"
        onClick={() => setShowReparent(true)}
        title={t('editor.move')}
        data-testid="document-move-btn"
      >
        <ArrowsLeftRight size={14} weight="duotone" />
      </Button>
      <Button
        variant="icon"
        size="sm"
        onClick={() => setDeleteConfirm(true)}
        title={t('common.delete')}
        className="text-accent-2-700"
        data-testid="document-delete-btn"
      >
        <Trash size={14} weight="duotone" />
      </Button>
      <Button
        onClick={() => void doSave()}
        disabled={status === 'idle' || status === 'saved' || status === 'saving'}
        title={t('editor.save')}
        data-testid="document-save-btn"
      >
        <FloppyDisk size={15} weight="duotone" />
        {status === 'saving' ? t('editor.saving') : t('editor.save')}
      </Button>
    </>
  )

  const editorSheet = (
    <MarkdownEditor
      key={`${docId}:${editorEpoch}`}
      ref={editorRef}
      initialContent={doc.content ?? ''}
      onDirty={markDirty}
      wsSlug={ws}
    />
  )

  // Mode rédaction plein écran : la feuille et rien d'autre, mêmes métriques.
  if (focusMode) {
    return (
      <div className="fixed inset-0 z-40 overflow-y-auto bg-paper" data-testid="document-editor">
        <div className="sticky top-0 z-10 flex items-center gap-3 bg-paper px-[30px] py-3.5">
          <span className="truncate text-[13px] text-ink/[0.5]">{title}</span>
          {statusNote}
          <span className="flex-1" />
          <Button onClick={() => void doSave()} disabled={status !== 'dirty' && status !== 'error'}>
            <FloppyDisk size={15} weight="duotone" /> {t('editor.save')}
          </Button>
          <Button
            variant="icon"
            size="sm"
            onClick={() => setFocusMode(false)}
            title={t('editor.focusExit')}
          >
            <ArrowsIn size={14} weight="duotone" />
          </Button>
        </div>
        <div className="mx-auto max-w-[820px] px-6 pb-32">
          <div className="doc-sheet wiki-prose">{editorSheet}</div>
        </div>
      </div>
    )
  }

  return (
    <div data-testid="document-editor">
      <DocumentShell
        kicker={[doc.functional_type_slug, blocSlug].filter(Boolean).join(' · ')}
        title={
          <Input
            value={title}
            onChange={(e) => { setTitle(e.target.value); markDirty() }}
            className="max-w-[20ch] border-0 bg-transparent px-0 text-[42px] leading-[1.1]
              tracking-[-0.03em] [font-family:var(--font-heading)] [font-weight:var(--font-heading-weight)]"
            data-testid="document-title-input"
          />
        }
        meta={
          <>
            {slugEdit ? (
              <form
                className="flex items-center gap-1"
                onSubmit={(e) => {
                  e.preventDefault()
                  const v = slugValue.trim()
                  if (v && !_SLUG_RE.test(v)) {
                    setSlugError(t('editor.slugInvalid'))
                    return
                  }
                  slugMutation.mutate(v || null)
                }}
              >
                <Input
                  value={slugValue}
                  onChange={(e) => { setSlugValue(e.target.value); setSlugError(null) }}
                  className="w-52 [font-family:var(--font-mono)] text-[12px]"
                  placeholder="mon-slug"
                  autoFocus
                />
                <Button type="submit" variant="ghost" size="sm">OK</Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => { setSlugEdit(false); setSlugValue(doc.slug ?? ''); setSlugError(null) }}
                >
                  {t('common.cancel')}
                </Button>
                {slugError && <span className="field-error">{slugError}</span>}
              </form>
            ) : (
              <button
                type="button"
                onClick={() => setSlugEdit(true)}
                className="inline-flex items-center gap-1 border-0 bg-transparent p-0 text-inherit hover:text-accent-700"
                title={t('editor.slugSet')}
              >
                <LinkSimple size={13} weight="duotone" />
                {doc.slug
                  ? <span className="[font-family:var(--font-mono)]">{doc.slug}</span>
                  : <span className="italic">{t('editor.slugAdd')}</span>}
              </button>
            )}
            <span>v{doc.version} · {t('editor.modifiedAt', { when: relativeDate(doc.updated_at) })}</span>
            <span className="flex-1" />
            {doc.exposed && <span className="tag tag-accent">{t('documents.public')}</span>}
          </>
        }
        actions={actions}
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
        {editorSheet}
      </DocumentShell>

      {showReparent && doc && (
        <ReparentDialog
          ws={ws!}
          block={blocSlug!}
          doc={{ id: doc.doc_technical_key, title: doc.title, type: doc.functional_type_slug }}
          onDone={() => {
            setShowReparent(false)
            void queryClient.invalidateQueries({ queryKey: ['document', ws, docId] })
            void queryClient.invalidateQueries({ queryKey: ['block-documents', ws, blocSlug] })
            void queryClient.invalidateQueries()
          }}
          onCancel={() => setShowReparent(false)}
        />
      )}

      {deleteConfirm && (
        <div className="dialog-backdrop z-50">
          <div className="dialog">
            <h4 className="dialog-title">{t('documents.deleteConfirmTitle')}</h4>
            <p className="dialog-body">{t('documents.deleteConfirmMsg')}</p>
            <div className="dialog-actions">
              <Button variant="secondary" onClick={() => setDeleteConfirm(false)} disabled={deleting}>
                {t('common.cancel')}
              </Button>
              <Button
                variant="danger"
                onClick={() => void deleteDocument()}
                disabled={deleting}
                data-testid="document-delete-confirm-btn"
              >
                {deleting ? t('common.loading') : t('documents.deleteConfirm')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {blocker.state === 'blocked' && (
        <div className="dialog-backdrop z-50">
          <div className="dialog">
            <h4 className="dialog-title">{t('editor.leaveConfirm.title')}</h4>
            <p className="dialog-body">{t('editor.leaveConfirm.message')}</p>
            {status === 'error' && errorMsg && <p className="field-error">{errorMsg}</p>}
            <div className="flex flex-col gap-2">
              <Button
                data-testid="leave-save-btn"
                onClick={async () => { const ok = await doSave(); if (ok) blocker.proceed() }}
                disabled={status === 'saving'}
              >
                {status === 'saving' ? t('editor.saving') : t('editor.leaveConfirm.save')}
              </Button>
              <Button variant="secondary" data-testid="leave-discard-btn" onClick={() => blocker.proceed()}>
                {t('editor.leaveConfirm.discard')}
              </Button>
              <Button variant="secondary" data-testid="leave-cancel-btn" onClick={() => blocker.reset()}>
                {t('editor.leaveConfirm.cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {conflict && (
        <ConflictResolver
          baseVersion={conflict.baseVersion}
          server={conflict.server}
          serverVersion={conflict.serverVersion}
          draft={conflict.draft}
          onResolve={resolveConflict}
          onCancel={() => { setConflict(null); setStatus('idle') }}
        />
      )}
    </div>
  )
}

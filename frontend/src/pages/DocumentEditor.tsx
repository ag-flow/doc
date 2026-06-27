import { useCallback, useEffect, useRef, useState } from 'react'
import { useBlocker, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Eye, EyeOff, Copy, Check } from 'lucide-react'
import { ApiError, docsApi, reactionsApi, type DocumentOut, type ReactionOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { PropertiesPanel } from '../components/PropertiesPanel'
import { ConflictResolver } from './ConflictResolver'
import { DocumentChildrenPanel } from '../components/DocumentChildrenPanel'
import { MarkdownEditor, type MarkdownEditorHandle } from '../components/MarkdownEditor'
import { ReactionBar } from '../components/ReactionBar'
import { CommentsPanel } from '../components/CommentsPanel'

type SaveStatus = 'idle' | 'dirty' | 'saving' | 'error'

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

  const [title, setTitle] = useState('')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [conflict, setConflict] = useState<ConflictData | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [copied, setCopied] = useState(false)

  const exposeMutation = useMutation({
    mutationFn: (value: boolean) => docsApi.setDocumentExposed(ws!, docId!, value),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: ['document', ws, docId] })
      void queryClient.setQueryData(['document', ws, docId], updated)
    },
  })

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

  useEffect(() => {
    if (!doc) return
    setTitle(doc.title)
    expectedVersion.current = doc.version
    ancestorRef.current = { title: doc.title, content: doc.content ?? '' }
  }, [doc])

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
      setStatus('idle')
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
      void queryClient.invalidateQueries({ queryKey: ['document', ws, docId] })
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

  return (
    <div className="p-6" data-testid="document-editor">
      <div className="mb-1 flex items-center gap-4">
        <Input
          value={title}
          onChange={(e) => { setTitle(e.target.value); markDirty() }}
          className="max-w-xl text-lg font-semibold"
          data-testid="document-title-input"
        />
        <div className="ml-auto flex items-center gap-3">
          {status === 'dirty' && (
            <span className="text-sm text-amber-600">{t('editor.dirty')}</span>
          )}
          {status === 'error' && (
            <span className="text-sm text-red-600" data-testid="document-error">
              {errorMsg ?? t('error.generic')}
            </span>
          )}

          {/* Bouton exposé / privé */}
          <button
            type="button"
            title={doc.exposed ? 'Rendre privé' : 'Exposer publiquement'}
            onClick={() => exposeMutation.mutate(!doc.exposed)}
            disabled={exposeMutation.isPending}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium
              transition-colors ${doc.exposed
                ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}
            data-testid="document-expose-btn"
          >
            {doc.exposed ? <Eye size={13} /> : <EyeOff size={13} />}
            {doc.exposed ? 'Public' : 'Privé'}
          </button>

          {/* Copier l'URL publique quand exposé */}
          {doc.exposed && (
            <button
              type="button"
              title="Copier le lien public"
              onClick={() => {
                void navigator.clipboard.writeText(
                  `${window.location.origin}/pub/${docId}`
                )
                setCopied(true)
                setTimeout(() => setCopied(false), 1500)
              }}
              className="flex items-center gap-1 rounded-md px-2 py-1.5 text-xs text-gray-400
                         hover:text-gray-600 hover:bg-gray-100 transition-colors"
            >
              {copied ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
            </button>
          )}

          <Button
            variant="danger"
            size="sm"
            onClick={() => setDeleteConfirm(true)}
            data-testid="document-delete-btn"
          >
            {t('common.delete')}
          </Button>
          <Button
            onClick={() => void doSave()}
            disabled={status === 'idle' || status === 'saving'}
            data-testid="document-save-btn"
          >
            {status === 'saving' ? t('editor.saving') : t('editor.save')}
          </Button>
        </div>
      </div>

      {doc.functional_type_slug && (
        <p className="mb-4 text-sm text-gray-400" data-testid="document-type-badge">
          {doc.functional_type_slug}
        </p>
      )}

      <div className="flex gap-6">
        <div className="w-2/3">
          <MarkdownEditor ref={editorRef} initialContent={doc.content ?? ''} onDirty={markDirty} />
          <DocumentChildrenPanel ws={ws} blocSlug={blocSlug} docId={docId} />
        </div>
        <div className="w-1/3 border-l border-gray-200 pl-6">
          <PropertiesPanel ws={ws} docId={docId} />
        </div>
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

      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold text-red-600">{t('documents.deleteConfirmTitle')}</h2>
            <p className="text-sm text-gray-600">{t('documents.deleteConfirmMsg')}</p>
            <div className="flex justify-end gap-2">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold">{t('editor.leaveConfirm.title')}</h2>
            <p className="text-sm text-gray-600">{t('editor.leaveConfirm.message')}</p>
            {status === 'error' && errorMsg && (
              <p className="text-sm text-red-600">{errorMsg}</p>
            )}
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

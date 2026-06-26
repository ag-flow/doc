import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ApiError, docsApi, type AllowedTypeOut, type DocumentOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { PropertiesPanel } from '../components/PropertiesPanel'
import { ConflictResolver } from '../components/ConflictResolver'
import {
  MarkdownEditor,
  type MarkdownEditorHandle,
} from '../components/MarkdownEditor'

type SaveStatus = 'idle' | 'dirty' | 'saving' | 'error'

interface ConflictData {
  ancestor: { title: string; content: string }
  server: { title: string; content: string; version: number }
  mine: { title: string; content: string }
}

export function DocumentEditor() {
  const { t } = useTranslation()
  // Route /ws/:wsSlug/blocs/:blocSlug/documents/:docId
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

  const [creatingChild, setCreatingChild] = useState<AllowedTypeOut | null>(null)
  const [childTitle, setChildTitle] = useState('')
  const [childSubmitting, setChildSubmitting] = useState(false)
  const [childError, setChildError] = useState<string | null>(null)

  const { data: childTypes = [] } = useQuery<AllowedTypeOut[]>({
    queryKey: ['allowed-types', ws, blocSlug, docId],
    queryFn: () => docsApi.getAllowedTypes(ws!, blocSlug!, docId),
    enabled: Boolean(ws && blocSlug && docId),
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

  const doSave = useCallback(async () => {
    if (!ws || !docId || !editorRef.current) return
    if (status !== 'dirty' && status !== 'error') return
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
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const server = (err.detail ?? {}) as Partial<DocumentOut>
        setConflict({
          ancestor: ancestorRef.current,
          server: {
            title: server.title ?? '',
            content: server.content ?? '',
            version: server.version ?? expectedVersion.current,
          },
          mine: { title, content },
        })
        setStatus('idle')
      } else if (err instanceof ApiError && err.status === 422) {
        setStatus('error')
        setErrorMsg(err.message)
      } else {
        setStatus('error')
        setErrorMsg(err instanceof ApiError ? err.message : t('error.generic'))
      }
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

  const keepServer = useCallback(
    (serverVersion: number) => {
      expectedVersion.current = serverVersion
      setConflict(null)
      void queryClient.invalidateQueries({ queryKey: ['document', ws, docId] })
    },
    [queryClient, ws, docId],
  )

  const keepMine = useCallback(() => {
    if (conflict) expectedVersion.current = conflict.server.version
    setConflict(null)
    void doSave()
  }, [conflict, doSave])

  async function createChild() {
    if (!childTitle.trim() || !creatingChild || !ws || !blocSlug || !docId) return
    setChildSubmitting(true)
    setChildError(null)
    try {
      const newDoc = await docsApi.createDocument(ws, blocSlug, {
        title: childTitle.trim(),
        functional_type_slug: creatingChild.slug,
        parent_id: docId,
      })
      setCreatingChild(null)
      setChildTitle('')
      void navigate(`/ws/${ws}/blocs/${blocSlug}/documents/${newDoc.doc_technical_key}`)
    } catch (err) {
      setChildError(err instanceof ApiError ? err.message : t('error.generic'))
      setChildSubmitting(false)
    }
  }

  if (isLoading) return <div className="p-8">{t('common.loading')}</div>
  if (!doc || !ws || !docId) return <div className="p-8">{t('error.notFound')}</div>

  return (
    <div className="p-6" data-testid="document-editor">
      <div className="mb-1 flex items-center gap-4">
        <Input
          value={title}
          onChange={(e) => {
            setTitle(e.target.value)
            markDirty()
          }}
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
          <MarkdownEditor
            ref={editorRef}
            initialContent={doc.content ?? ''}
            onDirty={markDirty}
          />
        </div>
        <div className="w-1/3 border-l border-gray-200 pl-6">
          <PropertiesPanel ws={ws} docId={docId} />
        </div>
      </div>

      {childTypes.length > 0 && (
        <div className="mt-6 flex items-center gap-2">
          <span className="text-sm text-gray-400">{t('documents.addChild')}</span>
          {childTypes.map((ct) => (
            <Button
              key={ct.slug}
              variant="secondary"
              size="sm"
              data-testid={`add-child-${ct.slug}`}
              onClick={() => { setCreatingChild(ct); setChildTitle(''); setChildError(null) }}
            >
              + {ct.label}
            </Button>
          ))}
        </div>
      )}

      {creatingChild && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold">+ {creatingChild.label}</h2>
            <div>
              <label className="mb-1 block text-sm font-medium">{t('documents.titleField')}</label>
              <Input
                value={childTitle}
                onChange={(e) => setChildTitle(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void createChild() }}
                placeholder="Titre…"
                autoFocus
                data-testid="child-title-input"
              />
            </div>
            {childError && <p className="text-sm text-red-600">{childError}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setCreatingChild(null)}>
                {t('common.cancel')}
              </Button>
              <Button
                disabled={!childTitle.trim() || childSubmitting}
                onClick={() => void createChild()}
                data-testid="child-submit"
              >
                {t('common.save')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {conflict && (
        <ConflictResolver
          ancestor={conflict.ancestor}
          server={conflict.server}
          mine={conflict.mine}
          onKeepServer={keepServer}
          onKeepMine={keepMine}
          onClose={() => setConflict(null)}
        />
      )}
    </div>
  )
}

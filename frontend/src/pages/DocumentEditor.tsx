import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ApiError, docsApi, type DocumentOut } from '../lib/api'
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
  const { wsSlug: ws, docId } = useParams<{ wsSlug: string; blocSlug: string; docId: string }>()
  const queryClient = useQueryClient()

  const editorRef = useRef<MarkdownEditorHandle>(null)
  const expectedVersion = useRef<number>(0)
  const ancestorRef = useRef<{ title: string; content: string }>({ title: '', content: '' })

  const [title, setTitle] = useState('')
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [conflict, setConflict] = useState<ConflictData | null>(null)

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
  }, [ws, docId, title, queryClient, t])

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
            disabled={status === 'saving'}
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

import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, type DocumentOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

export function DocumentTree() {
  const { t } = useTranslation()
  const { ws } = useParams<{ ws: string }>()
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const { data: documents = [], isLoading } = useQuery<DocumentOut[]>({
    queryKey: ['documents', ws],
    queryFn: () => api.get(`/workspaces/${ws}/documents`),
  })

  const createMutation = useMutation({
    mutationFn: (body: { title: string }) =>
      api.post<DocumentOut>(`/workspaces/${ws}/documents`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['documents', ws] })
      setCreating(false)
      setNewTitle('')
      setFormError(null)
    },
    onError: (err: Error) => setFormError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/workspaces/${ws}/documents/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents', ws] }),
  })

  if (isLoading) return <div className="p-8">{t('error.generic')}…</div>

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">{t('documents.title')}</h1>
        <Button onClick={() => setCreating((v) => !v)} data-testid="create-doc-btn">
          {t('documents.create')}
        </Button>
      </div>

      {creating && (
        <div className="mb-6 rounded border border-gray-200 bg-gray-50 p-4">
          <div className="max-w-sm">
            <label className="mb-1 block text-sm font-medium">{t('documents.titleField')}</label>
            <Input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Ma page"
              data-testid="title-input"
            />
          </div>
          {formError && <p className="mt-2 text-sm text-red-600">{formError}</p>}
          <div className="mt-3 flex gap-2">
            <Button
              onClick={() => newTitle && createMutation.mutate({ title: newTitle })}
              disabled={createMutation.isPending}
            >
              {t('types.save')}
            </Button>
            <Button variant="secondary" onClick={() => setCreating(false)}>
              {t('types.cancel')}
            </Button>
          </div>
        </div>
      )}

      {documents.length === 0 ? (
        <p className="text-gray-500">{t('documents.noDocuments')}</p>
      ) : (
        <ul className="space-y-2" data-testid="documents-list">
          {documents.map((doc) => (
            <li
              key={doc.doc_technical_key}
              className="flex items-center justify-between rounded border border-gray-200 px-4 py-2"
            >
              <span className="text-sm font-medium">
                {doc.parent_id && <span className="mr-2 text-gray-400">↳</span>}
                {doc.title}
              </span>
              <Button
                variant="danger"
                size="sm"
                onClick={() => deleteMutation.mutate(doc.doc_technical_key)}
                data-testid={`delete-doc-${doc.doc_technical_key}`}
              >
                {t('documents.delete')}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

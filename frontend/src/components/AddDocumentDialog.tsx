import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ApiError, docsApi, type AllowedTypeOut, type DocumentOut } from '../lib/api'
import { Button } from './ui/button'
import { Input } from './ui/input'

interface AddDocumentDialogProps {
  ws: string
  block: string
  parentId?: string
  onCreated: (docId: string) => void
  onClose: () => void
}

export function AddDocumentDialog({
  ws,
  block,
  parentId,
  onCreated,
  onClose,
}: AddDocumentDialogProps) {
  const { t } = useTranslation()
  const [title, setTitle] = useState('')
  const [selectedType, setSelectedType] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: types = [], isLoading } = useQuery<AllowedTypeOut[]>({
    queryKey: ['allowed-types', ws, block, parentId ?? null],
    queryFn: () => docsApi.getAllowedTypes(ws, block, parentId),
  })

  const effectiveType = types.length === 1 ? types[0].slug : selectedType

  async function handleSubmit() {
    if (!title.trim() || !effectiveType) return
    setSubmitting(true)
    setError(null)
    try {
      const doc: DocumentOut = await docsApi.createDocument(ws, block, {
        title: title.trim(),
        functional_type_slug: effectiveType,
        parent_id: parentId,
      })
      onCreated(doc.doc_technical_key)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('error.generic'))
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      data-testid="add-document-dialog"
    >
      <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow-xl">
        <h2 className="text-lg font-bold">{t('documents.add')}</h2>

        {isLoading ? (
          <p className="text-sm text-gray-400">{t('common.loading')}</p>
        ) : types.length === 0 ? (
          <p className="text-sm text-gray-500" data-testid="add-document-no-types">
            {t('documents.no_types')}
          </p>
        ) : (
          <>
            {types.length > 1 && (
              <div>
                <label className="mb-1 block text-sm font-medium">{t('documents.type')}</label>
                <select
                  className="block w-full rounded border border-gray-300 px-3 py-2 text-sm"
                  value={selectedType}
                  onChange={(e) => setSelectedType(e.target.value)}
                  data-testid="add-document-type-select"
                >
                  <option value="">{t('documents.selectType')}</option>
                  {types.map((ty) => (
                    <option key={ty.slug} value={ty.slug}>
                      {ty.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <label className="mb-1 block text-sm font-medium">{t('documents.titleField')}</label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ma page"
                data-testid="add-document-title-input"
              />
            </div>
          </>
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            disabled={submitting || isLoading || types.length === 0 || !title.trim() || !effectiveType}
            data-testid="add-document-submit"
          >
            {t('common.save')}
          </Button>
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ApiError, docsApi, type AllowedTypeOut, type DocumentOut } from '../lib/api'
import { Button } from './ui/button'
import { Input } from './ui/input'

function slugify(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
}

const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$/

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
  const qc = useQueryClient()
  const [title, setTitle] = useState('')
  const [slug, setSlug] = useState('')
  const [selectedType, setSelectedType] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Slugs des siblings depuis le cache (déjà chargé par BlockDocumentList)
  const siblingSlugSet = (() => {
    const cached = qc.getQueryData<DocumentOut[]>(['block-documents', ws, block])
    if (!cached) return new Set<string>()
    const pid = parentId ?? null
    return new Set(
      cached
        .filter((d) => (d.parent_id ?? null) === pid && d.slug)
        .map((d) => d.slug as string),
    )
  })()

  function handleTitleChange(v: string) {
    setTitle(v)
    setSlug(slugify(v))
  }

  function handleSlugChange(raw: string) {
    // Filtre immédiat : seuls [a-z0-9-] autorisés
    setSlug(raw.replace(/[^a-z0-9-]/g, '').slice(0, 80))
  }

  const { data: types = [], isLoading } = useQuery<AllowedTypeOut[]>({
    queryKey: ['allowed-types', ws, block, parentId ?? null],
    queryFn: () => docsApi.getAllowedTypes(ws, block, parentId),
  })

  const effectiveType = types.length === 1 ? types[0].slug : selectedType

  const slugTrimmed = slug.trim()
  const formatOk = slugTrimmed !== '' && SLUG_RE.test(slugTrimmed)
  const notDuplicate = !siblingSlugSet.has(slugTrimmed)
  const slugValid = formatOk && notDuplicate

  const slugError = slug
    ? !formatOk
      ? 'Commence et finit par un alphanumérique, 2–80 chars.'
      : !notDuplicate
        ? 'Ce slug est déjà utilisé par un document du même niveau.'
        : null
    : null

  async function handleSubmit() {
    if (!title.trim() || !effectiveType || !slugValid) return
    setSubmitting(true)
    setError(null)
    try {
      const doc: DocumentOut = await docsApi.createDocument(ws, block, {
        title: title.trim(),
        functional_type_slug: effectiveType,
        parent_id: parentId,
        slug: slugTrimmed,
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
                onChange={(e) => handleTitleChange(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void handleSubmit() }}
                placeholder="Ma page"
                data-testid="add-document-title-input"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-600">Slug</label>
              <Input
                value={slug}
                onChange={(e) => handleSlugChange(e.target.value)}
                placeholder="ma-page"
                className={slugError ? 'border-red-400 focus-visible:ring-red-400' : ''}
                data-testid="add-document-slug-input"
              />
              {slugError && (
                <p className="mt-1 text-xs text-red-500">{slugError}</p>
              )}
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
            disabled={submitting || isLoading || types.length === 0 || !title.trim() || !effectiveType || !slugValid}
            data-testid="add-document-submit"
          >
            {t('common.save')}
          </Button>
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { KeyRound, Trash2, Plus, Copy, Check } from 'lucide-react'
import { hmacSecretsApi, type HmacSecretOut } from '../lib/api'
import { Button } from './ui/button'
import { Input } from './ui/input'

const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/

/** Onglet de gestion des secrets HMAC (générer / coller, copier, supprimer). */
export function HmacSecretsTab() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const { data: secrets = [], isLoading } = useQuery<HmacSecretOut[]>({
    queryKey: ['hmac-secrets'],
    queryFn: () => hmacSecretsApi.list(),
  })

  const [showForm, setShowForm] = useState(false)
  const [label, setLabel] = useState('')
  const [slug, setSlug] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [value, setValue] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [createdValue, setCreatedValue] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<HmacSecretOut | null>(null)

  const createMutation = useMutation({
    mutationFn: () => hmacSecretsApi.create({ label, slug, value: value.trim() || undefined }),
    onSuccess: (created) => {
      void qc.invalidateQueries({ queryKey: ['hmac-secrets'] })
      setCreatedValue(created.value)
      resetForm()
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => hmacSecretsApi.delete(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['hmac-secrets'] })
      setDeleteTarget(null)
    },
  })

  function resetForm() {
    setShowForm(false)
    setLabel('')
    setSlug('')
    setSlugTouched(false)
    setValue('')
    setFormError(null)
  }

  function handleLabel(v: string) {
    setLabel(v)
    setFormError(null)
    if (!slugTouched) {
      setSlug(v.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9_-]/g, '').replace(/^[-_]+/, ''))
    }
  }

  async function copyText(text: string, id: string) {
    try {
      await navigator.clipboard?.writeText(text)
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 1500)
    } catch {
      /* presse-papier indisponible : on ignore silencieusement */
    }
  }

  async function copyRow(s: HmacSecretOut) {
    const revealed = await hmacSecretsApi.reveal(s.id)
    await copyText(revealed.value, s.id)
  }

  const canSubmit = Boolean(label.trim()) && SLUG_RE.test(slug)

  if (isLoading)
    return <div className="py-8 text-center text-sm text-gray-400">{t('common.loading')}</div>

  return (
    <>
      {createdValue && (
        <div
          className="mb-4 rounded-lg border border-green-200 bg-green-50 p-4"
          data-testid="hmac-created-banner"
        >
          <p className="mb-2 text-sm font-medium text-green-800">{t('hmac.createdOnce')}</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 truncate rounded bg-white px-3 py-2 font-mono text-xs text-gray-800">
              {createdValue}
            </code>
            <button
              onClick={() => copyText(createdValue, 'created')}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-800"
              title={t('hmac.copy')}
              data-testid="hmac-copy-created"
            >
              {copiedId === 'created' ? <Check size={16} className="text-green-600" /> : <Copy size={16} />}
            </button>
            <button
              onClick={() => setCreatedValue(null)}
              className="text-xs text-green-700 hover:underline"
            >
              {t('common.close')}
            </button>
          </div>
        </div>
      )}

      <div className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
        {secrets.length === 0 && !showForm && (
          <p className="px-6 py-8 text-center text-sm text-gray-400">{t('hmac.empty')}</p>
        )}

        {secrets.map((s) => (
          <div key={s.id} className="flex items-center gap-3 px-5 py-4" data-testid={`hmac-row-${s.slug}`}>
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-indigo-50 text-indigo-600">
              <KeyRound size={15} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-800">{s.label}</p>
              <p className="font-mono text-xs text-gray-400">{s.slug}</p>
            </div>
            <button
              onClick={() => copyRow(s)}
              className="rounded p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
              title={t('hmac.copy')}
              data-testid={`hmac-copy-${s.slug}`}
            >
              {copiedId === s.id ? <Check size={15} className="text-green-600" /> : <Copy size={15} />}
            </button>
            <button
              onClick={() => setDeleteTarget(s)}
              className="rounded p-1.5 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600"
              title={t('hmac.delete')}
              data-testid={`hmac-delete-${s.slug}`}
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}

        {showForm ? (
          <div className="space-y-3 px-5 py-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">{t('hmac.label')}</label>
                <Input
                  value={label}
                  onChange={(e) => handleLabel(e.target.value)}
                  placeholder="Workflow prod"
                  data-testid="hmac-label-input"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">{t('hmac.slug')}</label>
                <Input
                  value={slug}
                  onChange={(e) => { setSlug(e.target.value); setSlugTouched(true); setFormError(null) }}
                  placeholder="workflow-prod"
                  data-testid="hmac-slug-input"
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600">{t('hmac.value')}</label>
              <Input
                type="text"
                value={value}
                onChange={(e) => { setValue(e.target.value); setFormError(null) }}
                placeholder={t('hmac.valuePlaceholder')}
                data-testid="hmac-value-input"
              />
              <p className="mt-1 text-xs text-gray-400">{t('hmac.valueHint')}</p>
            </div>
            {formError && <p className="text-xs text-red-600" data-testid="hmac-form-error">{formError}</p>}
            <div className="flex gap-2">
              <Button
                onClick={() => createMutation.mutate()}
                disabled={!canSubmit || createMutation.isPending}
                data-testid="hmac-create-btn"
              >
                {createMutation.isPending
                  ? t('common.loading')
                  : value.trim()
                    ? t('hmac.add')
                    : t('hmac.addGenerate')}
              </Button>
              <Button variant="secondary" onClick={resetForm}>{t('common.cancel')}</Button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowForm(true)}
            className="flex w-full items-center gap-2 rounded-b-lg px-5 py-3 text-sm text-indigo-600 transition-colors hover:bg-indigo-50"
            data-testid="hmac-add-btn"
          >
            <Plus size={15} />
            {t('hmac.addBtn')}
          </button>
        )}
      </div>

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm space-y-4 rounded-xl bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold text-red-600">{t('hmac.deleteTitle')}</h2>
            <p className="text-sm text-gray-600">{t('hmac.deleteConfirm', { name: deleteTarget.label })}</p>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setDeleteTarget(null)} disabled={deleteMutation.isPending}>
                {t('common.cancel')}
              </Button>
              <Button
                variant="danger"
                onClick={() => deleteMutation.mutate(deleteTarget.id)}
                disabled={deleteMutation.isPending}
                data-testid="hmac-delete-confirm-btn"
              >
                {deleteMutation.isPending ? t('common.loading') : t('common.delete')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

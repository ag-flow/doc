import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { LockKeyhole, Trash2, Plus } from 'lucide-react'
import { secretsApi, type VaultSecretOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

export function VaultSecretsTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const { data: secrets = [], isLoading } = useQuery<VaultSecretOut[]>({
    queryKey: ['user-secrets'],
    queryFn: () => secretsApi.list(),
  })

  const [showForm, setShowForm] = useState(false)
  const [label, setLabel] = useState('')
  const [slug, setSlug] = useState('')
  const [value, setValue] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<VaultSecretOut | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () => secretsApi.create({ label, slug, value }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['user-secrets'] })
      setShowForm(false)
      setLabel('')
      setSlug('')
      setValue('')
      setFormError(null)
    },
    onError: (err: Error) => setFormError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => secretsApi.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['user-secrets'] })
      setDeleteTarget(null)
      setDeleteError(null)
    },
    onError: (err: Error) => setDeleteError(err.message),
  })

  // Dérive le slug automatiquement depuis le label si l'utilisateur n'a pas encore modifié le slug
  const [slugTouched, setSlugTouched] = useState(false)
  function handleLabelChange(v: string) {
    setLabel(v)
    setFormError(null)
    if (!slugTouched) {
      setSlug(v.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9_-]/g, '').replace(/^[-_]+/, ''))
    }
  }

  function resetForm() {
    setShowForm(false)
    setLabel('')
    setSlug('')
    setValue('')
    setSlugTouched(false)
    setFormError(null)
  }

  const canSubmit = label.trim() && /^[a-z0-9][a-z0-9_-]*$/.test(slug) && value.trim()

  if (isLoading) return <div className="py-8 text-center text-sm text-gray-400">{t('common.loading')}</div>

  return (
    <>
      <div className="rounded-lg border border-gray-200 bg-white divide-y divide-gray-100">
        {secrets.length === 0 && !showForm && (
          <p className="px-6 py-8 text-center text-sm text-gray-400">{t('vault.secrets.empty')}</p>
        )}

        {secrets.map((s) => (
          <div key={s.id} className="flex items-center gap-3 px-5 py-4">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-amber-50 text-amber-600 shrink-0">
              <LockKeyhole size={15} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-800">{s.label}</p>
              <p className="text-xs text-gray-400 font-mono">{s.slug}</p>
            </div>
            <button
              onClick={() => { setDeleteTarget(s); setDeleteError(null) }}
              className="rounded p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 transition-colors"
              title={t('vault.delete')}
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}

        {showForm ? (
          <div className="px-5 py-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">{t('vault.secrets.label')}</label>
                <Input
                  value={label}
                  onChange={(e) => handleLabelChange(e.target.value)}
                  placeholder="Ma clé API"
                  data-testid="secret-label-input"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">{t('vault.secrets.slug')}</label>
                <Input
                  value={slug}
                  onChange={(e) => { setSlug(e.target.value); setSlugTouched(true); setFormError(null) }}
                  placeholder="ma-cle-api"
                  data-testid="secret-slug-input"
                />
                <p className="mt-1 text-xs text-gray-400">{t('vault.secrets.slugHint')}</p>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-600">{t('vault.secrets.value')}</label>
              <Input
                type="password"
                value={value}
                onChange={(e) => { setValue(e.target.value); setFormError(null) }}
                placeholder="••••••••••••"
                data-testid="secret-value-input"
              />
            </div>
            {formError && <p className="text-xs text-red-600" data-testid="secret-form-error">{formError}</p>}
            <div className="flex gap-2">
              <Button
                onClick={() => createMutation.mutate()}
                disabled={!canSubmit || createMutation.isPending}
                data-testid="secret-create-btn"
              >
                {createMutation.isPending ? t('common.loading') : t('vault.secrets.add')}
              </Button>
              <Button variant="secondary" onClick={resetForm}>
                {t('common.cancel')}
              </Button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowForm(true)}
            className="flex w-full items-center gap-2 px-5 py-3 text-sm text-amber-600 hover:bg-amber-50 transition-colors rounded-b-lg"
            data-testid="secret-add-btn"
          >
            <Plus size={15} />
            {t('vault.secrets.addBtn')}
          </button>
        )}
      </div>

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold text-red-600">{t('vault.secrets.deleteTitle')}</h2>
            <p className="text-sm text-gray-600">
              {t('vault.secrets.deleteConfirm', { name: deleteTarget.label })}
            </p>
            {deleteError && <p className="text-sm text-red-600">{deleteError}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => { setDeleteTarget(null); setDeleteError(null) }} disabled={deleteMutation.isPending}>
                {t('common.cancel')}
              </Button>
              <Button
                variant="danger"
                onClick={() => deleteMutation.mutate(deleteTarget.id)}
                disabled={deleteMutation.isPending}
                data-testid="secret-delete-confirm-btn"
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

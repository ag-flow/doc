import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, type FunctionalType } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

export function TypesAdmin() {
  const { t } = useTranslation()
  const { ws } = useParams<{ ws: string }>()
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [newSlug, setNewSlug] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newParent, setNewParent] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const { data: types = [], isLoading } = useQuery<FunctionalType[]>({
    queryKey: ['types', ws],
    queryFn: () => api.get(`/workspaces/${ws}/types`),
  })

  const createMutation = useMutation({
    mutationFn: (body: { slug: string; label: string; parent_slug?: string }) =>
      api.post<FunctionalType>(`/workspaces/${ws}/types`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['types', ws] })
      setCreating(false)
      setNewSlug('')
      setNewLabel('')
      setNewParent('')
      setFormError(null)
    },
    onError: (err: Error) => setFormError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (slug: string) => api.delete(`/workspaces/${ws}/types/${slug}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['types', ws] }),
  })

  function handleCreate() {
    if (!newSlug || !newLabel) return
    createMutation.mutate({ slug: newSlug, label: newLabel, parent_slug: newParent || undefined })
  }

  if (isLoading) return <div className="p-8">{t('error.generic')}…</div>

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">{t('types.title')}</h1>
        <Button onClick={() => setCreating((v) => !v)} data-testid="create-type-btn">
          {t('types.create')}
        </Button>
      </div>

      {creating && (
        <div className="mb-6 rounded border border-gray-200 bg-gray-50 p-4">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">{t('types.slug')}</label>
              <Input
                value={newSlug}
                onChange={(e) => setNewSlug(e.target.value)}
                placeholder="mon-type"
                data-testid="slug-input"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">{t('types.label')}</label>
              <Input
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                placeholder="Mon type"
                data-testid="label-input"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">{t('types.parent')}</label>
              <select
                className="block w-full rounded border border-gray-300 px-3 py-2 text-sm"
                value={newParent}
                onChange={(e) => setNewParent(e.target.value)}
                data-testid="parent-select"
              >
                <option value="">{t('types.none')}</option>
                {types.map((t) => (
                  <option key={t.slug} value={t.slug}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {formError && <p className="mt-2 text-sm text-red-600">{formError}</p>}
          <div className="mt-3 flex gap-2">
            <Button onClick={handleCreate} disabled={createMutation.isPending}>
              {t('types.save')}
            </Button>
            <Button variant="secondary" onClick={() => setCreating(false)}>
              {t('types.cancel')}
            </Button>
          </div>
        </div>
      )}

      <table className="w-full border-collapse" data-testid="types-table">
        <thead>
          <tr className="border-b text-left text-sm font-medium text-gray-500">
            <th className="pb-2 pr-4">{t('types.slug')}</th>
            <th className="pb-2 pr-4">{t('types.label')}</th>
            <th className="pb-2 pr-4">{t('types.parent')}</th>
            <th className="pb-2" />
          </tr>
        </thead>
        <tbody>
          {types.map((type) => (
            <tr key={type.slug} className="border-b hover:bg-gray-50">
              <td className="py-2 pr-4 font-mono text-sm">{type.slug}</td>
              <td className="py-2 pr-4 text-sm">{type.label}</td>
              <td className="py-2 pr-4 text-sm text-gray-500">{type.parent_slug ?? '—'}</td>
              <td className="py-2 text-right">
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => deleteMutation.mutate(type.slug)}
                  data-testid={`delete-${type.slug}`}
                >
                  {t('types.delete')}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

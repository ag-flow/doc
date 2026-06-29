import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../lib/api'
import type { FunctionalTypeRich, TemplateInfo } from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { TypePropertiesPanel } from '../components/TypePropertiesPanel'

export function TypesAdmin() {
  const { t } = useTranslation()
  // Route sous /ws/:wsSlug/types — le paramètre s'appelle wsSlug
  const { wsSlug: ws } = useParams<{ wsSlug: string }>()
  const queryClient = useQueryClient()

  const [creating, setCreating] = useState(false)
  const [newSlug, setNewSlug] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newParent, setNewParent] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const [showImport, setShowImport] = useState(false)
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [importMsg, setImportMsg] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [expandedType, setExpandedType] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const { data: types = [], isLoading } = useQuery<FunctionalTypeRich[]>({
    queryKey: ['types-rich', ws],
    queryFn: () => api.get(`/workspaces/${ws}/types/rich`),
  })

  const { data: templates = [] } = useQuery<TemplateInfo[]>({
    queryKey: ['templates'],
    queryFn: () => api.get<TemplateInfo[]>('/templates'),
    enabled: showImport,
  })

  const createMutation = useMutation({
    mutationFn: (body: { slug: string; label: string; parent_slug?: string }) =>
      api.post<FunctionalTypeRich>(`/workspaces/${ws}/types`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['types-rich', ws] })
      setCreating(false)
      setNewSlug('')
      setNewLabel('')
      setNewParent('')
      setSlugTouched(false)
      setFormError(null)
    },
    onError: (err: Error) => setFormError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (slug: string) => api.delete(`/workspaces/${ws}/types/${slug}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['types-rich', ws] })
      setDeleteTarget(null)
      setDeleteError(null)
    },
    onError: (err: Error) => setDeleteError(err.message),
  })

  const importMutation = useMutation({
    mutationFn: (template: string) =>
      api.post<{ applied: boolean; no_op: boolean; adds: number; soft_updates: number }>(
        `/workspaces/${ws}/templates/import`,
        { template },
      ),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['types-rich', ws] })
      if (result.no_op) {
        setImportMsg(t('tpl.importNoOp'))
      } else {
        setImportMsg(t('tpl.importSuccess', { adds: result.adds, updates: result.soft_updates }))
      }
      setImportError(null)
    },
    onError: (err: Error) => setImportError(err.message),
  })

  function handleCreate() {
    if (!newSlug || !newLabel) return
    createMutation.mutate({ slug: newSlug, label: newLabel, parent_slug: newParent || undefined })
  }

  function openImportModal() {
    setShowImport(true)
    setSelectedTemplate('')
    setImportMsg(null)
    setImportError(null)
  }

  function closeImportModal() {
    setShowImport(false)
    setImportMsg(null)
    setImportError(null)
  }

  if (isLoading) return <div className="p-8">{t('common.loading')}…</div>

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center gap-3">
        <h1 className="text-2xl font-semibold text-gray-900 mr-auto">{t('types.title')}</h1>
        <Button variant="secondary" onClick={openImportModal} data-testid="import-template-btn">
          {t('tpl.importFromTemplate')}
        </Button>
        <Button onClick={() => setCreating((v) => !v)} data-testid="create-type-btn">
          {t('types.create')}
        </Button>
      </div>

      {creating && (
        <form
          className="mb-6 rounded border border-gray-200 bg-gray-50 p-4"
          onSubmit={(e) => { e.preventDefault(); handleCreate() }}
        >
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">{t('types.label')}</label>
              <Input
                value={newLabel}
                onChange={(e) => {
                  setNewLabel(e.target.value)
                  if (!slugTouched) setNewSlug(labelToSlug(e.target.value))
                }}
                placeholder="Mon type"
                data-testid="label-input"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">{t('types.slug')}</label>
              <Input
                value={newSlug}
                onChange={(e) => { setSlugTouched(true); setNewSlug(e.target.value) }}
                placeholder="mon-type"
                data-testid="slug-input"
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
                {types.map((ty) => (
                  <option key={ty.slug} value={ty.slug}>{ty.label}</option>
                ))}
              </select>
            </div>
          </div>
          {formError && <p className="mt-2 text-sm text-red-600">{formError}</p>}
          <div className="mt-3 flex gap-2">
            <Button type="submit" disabled={createMutation.isPending}>
              {t('types.save')}
            </Button>
            <Button variant="secondary" type="button" onClick={() => setCreating(false)}>
              {t('types.cancel')}
            </Button>
          </div>
        </form>
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
            <>
              <tr
                key={type.slug}
                className="border-b hover:bg-gray-50 cursor-pointer"
                onClick={() => setExpandedType((v) => (v === type.slug ? null : type.slug))}
                data-testid={`type-row-${type.slug}`}
              >
                <td className="py-2 pr-4 font-mono text-sm">
                  <span className="mr-1 text-gray-400 text-xs">
                    {expandedType === type.slug ? '▾' : '▸'}
                  </span>
                  {type.slug}
                </td>
                <td className="py-2 pr-4 text-sm">{type.label}</td>
                <td className="py-2 pr-4 text-sm text-gray-500">{type.parent_slug ?? '—'}</td>
                <td className="py-2 text-right" onClick={(e) => e.stopPropagation()}>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => { setDeleteTarget(type.slug); setDeleteError(null) }}
                    data-testid={`delete-${type.slug}`}
                  >
                    {t('types.delete')}
                  </Button>
                </td>
              </tr>
              {expandedType === type.slug && (
                <tr key={`${type.slug}-props`}>
                  <td colSpan={4} className="p-0">
                    <TypePropertiesPanel ws={ws!} type={type} />
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold text-red-600">{t('types.deleteConfirmTitle')}</h2>
            <p className="text-sm text-gray-600">
              {t('types.deleteConfirmMsg', { slug: deleteTarget })}
            </p>
            {deleteError && <p className="text-sm text-red-600">{deleteError}</p>}
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => { setDeleteTarget(null); setDeleteError(null) }}
                disabled={deleteMutation.isPending}
              >
                {t('common.cancel')}
              </Button>
              <Button
                variant="danger"
                onClick={() => deleteMutation.mutate(deleteTarget)}
                disabled={deleteMutation.isPending}
                data-testid="delete-type-confirm-btn"
              >
                {deleteMutation.isPending ? t('common.loading') : t('common.delete')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {showImport && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" data-testid="import-tpl-modal">
          <div className="bg-white rounded-lg p-6 max-w-sm w-full space-y-4">
            <h2 className="text-lg font-bold">{t('tpl.importFromTemplate')}</h2>
            <select
              className="block w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={selectedTemplate}
              onChange={e => setSelectedTemplate(e.target.value)}
              data-testid="template-select"
            >
              <option value="">{t('tpl.selectTemplate')}</option>
              {templates.map(tpl => (
                <option key={tpl.template} value={tpl.template}>
                  {tpl.label} (v{tpl.version})
                </option>
              ))}
            </select>
            {importError && <p className="text-sm text-red-600" data-testid="import-tpl-error">{importError}</p>}
            {importMsg && <p className="text-sm text-green-600" data-testid="import-tpl-success">{importMsg}</p>}
            <div className="flex gap-2">
              <Button
                disabled={!selectedTemplate || importMutation.isPending}
                onClick={() => importMutation.mutate(selectedTemplate)}
                data-testid="confirm-import-tpl-btn"
              >
                {importMutation.isPending ? t('common.loading') : t('tpl.importConfirm')}
              </Button>
              <Button variant="secondary" onClick={closeImportModal}>
                {importMsg ? t('common.close') : t('common.cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

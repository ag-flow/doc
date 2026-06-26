import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, templatesApi } from '../lib/api'
import type { TemplateInfo } from '../lib/api'
import { Button } from '../components/ui/button'
import { YamlEditor, type YamlEditorHandle } from '../components/YamlEditor'

export default function TemplateList() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const editorRef = useRef<YamlEditorHandle>(null)

  const [editTarget, setEditTarget] = useState<TemplateInfo | null>(null)
  const [yamlContent, setYamlContent] = useState<string | null>(null)
  const [yamlLoadError, setYamlLoadError] = useState<string | null>(null)
  const [editSaving, setEditSaving] = useState(false)
  const [editSaveError, setEditSaveError] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<TemplateInfo | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery<TemplateInfo[]>({
    queryKey: ['templates'],
    queryFn: () => api.get<TemplateInfo[]>('/templates'),
  })

  async function openEdit(tpl: TemplateInfo) {
    setEditTarget(tpl)
    setYamlContent(null)
    setYamlLoadError(null)
    setEditSaveError(null)
    try {
      const content = await templatesApi.getYaml(tpl.template)
      setYamlContent(content)
    } catch (e) {
      setYamlLoadError((e as Error).message)
    }
  }

  function closeEdit() {
    setEditTarget(null)
    setYamlContent(null)
    setYamlLoadError(null)
    setEditSaveError(null)
  }

  async function saveEdit() {
    if (!editTarget || !editorRef.current) return
    const content = editorRef.current.getValue()
    setEditSaving(true)
    setEditSaveError(null)
    try {
      await templatesApi.saveYaml(editTarget.template, content)
      void qc.invalidateQueries({ queryKey: ['templates'] })
      closeEdit()
    } catch (e) {
      setEditSaveError((e as Error).message)
    } finally {
      setEditSaving(false)
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await templatesApi.delete(deleteTarget.template)
      void qc.invalidateQueries({ queryKey: ['templates'] })
      setDeleteTarget(null)
    } catch (e) {
      setDeleteError((e as Error).message)
    } finally {
      setDeleting(false)
    }
  }

  if (isLoading) {
    return <div className="p-6 text-sm text-gray-500" data-testid="loading">{t('common.loading')}</div>
  }
  if (isError) {
    return <div className="p-6 text-sm text-red-600" data-testid="error">{t('error.generic')}</div>
  }
  if (!data?.length) {
    return (
      <div className="p-6 text-center text-gray-400" data-testid="empty">
        <p className="text-lg font-medium mb-2">{t('tpl.emptyTitle')}</p>
        <p className="text-sm">{t('tpl.emptyHint')}</p>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto" data-testid="template-list">
      <h1 className="text-2xl font-bold mb-6">{t('tpl.title')}</h1>
      <div className="grid gap-4">
        {data.map(tpl => (
          <div
            key={tpl.template}
            className="border rounded-lg p-4 bg-white shadow-sm"
            data-testid={`tpl-card-${tpl.template}`}
          >
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-2">
                  <span className="font-mono text-sm font-semibold text-indigo-700">{tpl.template}</span>
                  <span className="font-mono text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded">
                    v{tpl.version}
                  </span>
                  <span className="text-gray-700 font-medium">{tpl.label}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {tpl.type_slugs.map(slug => (
                    <span key={slug} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono">
                      {slug}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex gap-2 shrink-0">
                <Button size="sm" variant="secondary" onClick={() => void openEdit(tpl)} data-testid={`edit-btn-${tpl.template}`}>
                  {t('common.edit')}
                </Button>
                <Button size="sm" variant="danger" onClick={() => { setDeleteTarget(tpl); setDeleteError(null) }} data-testid={`delete-btn-${tpl.template}`}>
                  {t('common.delete')}
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Modale édition YAML ── */}
      {editTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="edit-modal">
          <div className="flex flex-col w-full max-w-4xl bg-white rounded-lg shadow-xl overflow-hidden" style={{ maxHeight: '90vh' }}>
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-bold">
                {t('tpl.editTitle', { template: editTarget.template })}
              </h2>
              <button className="text-gray-400 hover:text-gray-700 text-sm" onClick={closeEdit}>✕</button>
            </div>
            <div className="p-4">
              {yamlLoadError && (
                <p className="text-sm text-red-600 mb-2">{yamlLoadError}</p>
              )}
              {yamlContent === null && !yamlLoadError && (
                <p className="text-sm text-gray-400">{t('common.loading')}</p>
              )}
              {yamlContent !== null && (
                <div className="border border-gray-200 rounded overflow-hidden" style={{ height: '60vh' }}>
                  <YamlEditor ref={editorRef} initialValue={yamlContent} />
                </div>
              )}
            </div>
            {editSaveError && (
              <p className="px-6 pb-2 text-sm text-red-600" data-testid="edit-error">{editSaveError}</p>
            )}
            <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-200">
              <Button variant="secondary" onClick={closeEdit} disabled={editSaving}>
                {t('common.cancel')}
              </Button>
              <Button
                onClick={() => void saveEdit()}
                disabled={editSaving || yamlContent === null}
                data-testid="edit-save-btn"
              >
                {editSaving ? t('common.loading') : t('common.save')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modale confirmation suppression ── */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="delete-modal">
          <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold text-red-600">{t('tpl.deleteTitle')}</h2>
            <p className="text-sm text-gray-600">
              {t('tpl.deleteConfirm', { template: deleteTarget.template })}
            </p>
            {deleteError && <p className="text-sm text-red-600">{deleteError}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                {t('common.cancel')}
              </Button>
              <Button variant="danger" onClick={() => void confirmDelete()} disabled={deleting} data-testid="delete-confirm-btn">
                {deleting ? t('common.loading') : t('common.delete')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

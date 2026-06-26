import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../lib/api'
import type { TemplateInfo, WorkspaceOut } from '../lib/api'
import { Button } from '../components/ui/button'

export default function TemplateList() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [importTarget, setImportTarget] = useState<TemplateInfo | null>(null)
  const [selectedWs, setSelectedWs] = useState('')
  const [importResult, setImportResult] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery<TemplateInfo[]>({
    queryKey: ['templates'],
    queryFn: () => api.get<TemplateInfo[]>('/templates'),
  })

  const { data: workspaces = [] } = useQuery<WorkspaceOut[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get<WorkspaceOut[]>('/workspaces'),
    enabled: importTarget !== null,
  })

  const importMutation = useMutation({
    mutationFn: ({ wsSlug, template }: { wsSlug: string; template: string }) =>
      api.post<{ applied: boolean; no_op: boolean; adds: number; soft_updates: number }>(
        `/workspaces/${wsSlug}/templates/import`,
        { template },
      ),
    onSuccess: (result, { wsSlug }) => {
      void qc.invalidateQueries({ queryKey: ['types', wsSlug] })
      if (result.no_op) {
        setImportResult(t('tpl.importNoOp'))
      } else {
        void navigate(`/workspaces/${wsSlug}/types`)
      }
    },
    onError: (e: Error) => setImportError(e.message),
  })

  function openImportModal(tpl: TemplateInfo) {
    setImportTarget(tpl)
    setSelectedWs('')
    setImportResult(null)
    setImportError(null)
  }

  function closeModal() {
    setImportTarget(null)
    setImportResult(null)
    setImportError(null)
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
            className="border rounded-lg p-4 bg-white shadow-sm hover:shadow-md transition-shadow"
            data-testid={`tpl-card-${tpl.template}`}
          >
            <div className="flex items-center gap-3 mb-2">
              <span className="font-mono text-sm font-semibold text-indigo-700">{tpl.template}</span>
              <span className="font-mono text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded">
                v{tpl.version}
              </span>
              <span className="text-gray-700 font-medium">{tpl.label}</span>
            </div>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {tpl.type_slugs.map(slug => (
                <span key={slug} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono">
                  {slug}
                </span>
              ))}
            </div>
            <Button
              onClick={() => openImportModal(tpl)}
              data-testid={`import-btn-${tpl.template}`}
            >
              {t('tpl.importBtn')}
            </Button>
          </div>
        ))}
      </div>

      {importTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" data-testid="import-modal">
          <div className="bg-white rounded-lg p-6 max-w-sm w-full space-y-4">
            <h2 className="text-lg font-bold">{t('tpl.importModalTitle')}</h2>
            <p className="text-sm text-gray-600">
              {t('tpl.importModalDesc', { template: importTarget.template })}
            </p>
            <select
              className="block w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={selectedWs}
              onChange={e => setSelectedWs(e.target.value)}
              data-testid="ws-select"
            >
              <option value="">{t('tpl.selectWorkspace')}</option>
              {workspaces.map(ws => (
                <option key={ws.slug} value={ws.slug}>{ws.label} ({ws.slug})</option>
              ))}
            </select>
            {importError && <p className="text-sm text-red-600" data-testid="import-error">{importError}</p>}
            {importResult && <p className="text-sm text-green-600">{importResult}</p>}
            <div className="flex gap-2">
              <Button
                disabled={!selectedWs || importMutation.isPending}
                onClick={() => importMutation.mutate({ wsSlug: selectedWs, template: importTarget.template })}
                data-testid="confirm-import-btn"
              >
                {importMutation.isPending ? t('common.loading') : t('tpl.importConfirm')}
              </Button>
              <Button variant="secondary" onClick={closeModal}>{t('common.cancel')}</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

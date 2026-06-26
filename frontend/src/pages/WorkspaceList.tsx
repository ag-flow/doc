import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../lib/api'
import type { WorkspaceOut } from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/

export default function WorkspaceList() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const qc = useQueryClient()
  const { setCurrentSlug } = useWorkspace()

  // Message de redirection depuis WorkspaceLayout (ws invalide ou archivé)
  const redirectState = location.state as { invalidWs?: string; archivedWs?: string } | null
  const redirectMsg = redirectState?.invalidWs
    ? t('ws.notFound', { slug: redirectState.invalidWs })
    : redirectState?.archivedWs
      ? t('ws.archived', { slug: redirectState.archivedWs })
      : null

  const [showCreate, setShowCreate] = useState(false)
  const [slug, setSlug] = useState('')
  const [label, setLabel] = useState('')
  const [description, setDescription] = useState('')
  const [slugError, setSlugError] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceOut | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [apiError, setApiError] = useState('')

  const { data: workspaces = [], isLoading } = useQuery<WorkspaceOut[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get<WorkspaceOut[]>('/workspaces'),
  })

  const createMutation = useMutation({
    mutationFn: () => api.post<WorkspaceOut>('/workspaces', { slug, label, description: description || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workspaces'] })
      setShowCreate(false)
      setSlug('')
      setLabel('')
      setDescription('')
      setSlugTouched(false)
      setApiError('')
    },
    onError: (e: Error) => setApiError(e.message),
  })

  const archiveMutation = useMutation({
    mutationFn: (s: string) => api.post<WorkspaceOut>(`/workspaces/${s}/archive`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workspaces'] }),
    onError: (e: Error) => setApiError(e.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (s: string) => api.delete(`/workspaces/${s}?confirm=${encodeURIComponent(s)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workspaces'] })
      setDeleteTarget(null)
      setDeleteConfirm('')
    },
    onError: (e: Error) => setApiError(e.message),
  })

  const validateSlug = (v: string) => {
    if (!SLUG_RE.test(v)) setSlugError(t('ws.slugInvalid'))
    else setSlugError('')
  }

  const handleSelect = (ws: WorkspaceOut) => {
    setCurrentSlug(ws.slug)
    navigate(`/ws/${ws.slug}/blocs`)
  }

  if (isLoading) return <p className="p-4">{t('common.loading')}</p>

  return (
    <div className="p-6 max-w-3xl mx-auto" data-testid="workspace-list">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{t('ws.title')}</h1>
        <Button onClick={() => setShowCreate(true)} data-testid="create-ws-btn">
          {t('ws.create')}
        </Button>
      </div>

      {redirectMsg && (
        <p className="mb-4 rounded border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-800" data-testid="redirect-msg">
          {redirectMsg}
        </p>
      )}

      {apiError && (
        <p className="text-red-600 mb-4" data-testid="api-error">{apiError}</p>
      )}

      {showCreate && (
        <form
          data-testid="create-ws-form"
          className="mb-6 p-4 border rounded space-y-3"
          onSubmit={e => { e.preventDefault(); if (!slugError) createMutation.mutate() }}
        >
          <div>
            <label className="block text-sm font-medium mb-1">{t('ws.label')}</label>
            <Input
              data-testid="label-input"
              value={label}
              onChange={e => {
                setLabel(e.target.value)
                if (!slugTouched) {
                  const derived = labelToSlug(e.target.value)
                  setSlug(derived)
                  validateSlug(derived)
                }
              }}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">{t('ws.slug')}</label>
            <Input
              data-testid="slug-input"
              value={slug}
              onChange={e => { setSlugTouched(true); setSlug(e.target.value); validateSlug(e.target.value) }}
              placeholder="mon-workspace"
              required
            />
            {slugError && <p className="text-red-500 text-xs mt-1">{slugError}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">{t('ws.description')}</label>
            <Input
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={!!slugError || createMutation.isPending}>
              {t('common.save')}
            </Button>
            <Button variant="secondary" type="button" onClick={() => setShowCreate(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      )}

      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b text-left">
            <th className="py-2 pr-4">{t('ws.slug')}</th>
            <th className="py-2 pr-4">{t('ws.label')}</th>
            <th className="py-2">{t('common.actions')}</th>
          </tr>
        </thead>
        <tbody>
          {workspaces.map(ws => (
            <tr key={ws.slug} className="border-b hover:bg-gray-50" data-testid={`ws-row-${ws.slug}`}>
              <td className="py-2 pr-4 font-mono text-xs">{ws.slug}</td>
              <td className="py-2 pr-4">{ws.label}</td>
              <td className="py-2 flex gap-2">
                <Button
                  data-testid={`select-ws-${ws.slug}`}
                  onClick={() => handleSelect(ws)}
                >
                  {t('ws.select')}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => archiveMutation.mutate(ws.slug)}
                  disabled={archiveMutation.isPending}
                >
                  {t('ws.archive')}
                </Button>
                <Button
                  variant="danger"
                  data-testid={`delete-ws-${ws.slug}`}
                  onClick={() => { setDeleteTarget(ws); setDeleteConfirm('') }}
                >
                  {t('common.delete')}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {deleteTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" data-testid="delete-modal">
          <div className="bg-white rounded-lg p-6 max-w-sm w-full space-y-4">
            <h2 className="text-lg font-bold text-red-600">{t('ws.deleteConfirmTitle')}</h2>
            <p className="text-sm">
              {t('ws.deleteConfirmMsg', { slug: deleteTarget.slug })}
            </p>
            <Input
              data-testid="delete-confirm-input"
              value={deleteConfirm}
              onChange={e => setDeleteConfirm(e.target.value)}
              placeholder={deleteTarget.slug}
            />
            <div className="flex gap-2">
              <Button
                variant="danger"
                data-testid="confirm-delete-btn"
                disabled={deleteConfirm !== deleteTarget.slug || deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(deleteTarget.slug)}
              >
                {t('ws.deleteConfirm')}
              </Button>
              <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
                {t('common.cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

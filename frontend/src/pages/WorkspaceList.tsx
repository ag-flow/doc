import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Archive, ArrowRight, Plus, Search, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import type { WorkspaceOut } from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/

// Couleur du monogramme dérivée du slug (stable, variée entre workspaces).
const MONOGRAM_COLORS = [
  'bg-indigo-500', 'bg-emerald-500', 'bg-rose-500', 'bg-amber-500',
  'bg-sky-500', 'bg-violet-500', 'bg-teal-500', 'bg-fuchsia-500',
]
function monogramColor(slug: string): string {
  let h = 0
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) >>> 0
  return MONOGRAM_COLORS[h % MONOGRAM_COLORS.length]
}

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
  const [filter, setFilter] = useState('')

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
    <div className="p-6 sm:p-8 max-w-5xl mx-auto" data-testid="workspace-list">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t('ws.title')}</h1>
          <p className="mt-1 text-sm text-gray-500">{t('ws.subtitle')}</p>
        </div>
        <Button
          onClick={() => { setSlug(''); setSlugTouched(false); setShowCreate(true) }}
          data-testid="create-ws-btn"
          className="inline-flex shrink-0 items-center gap-1.5"
        >
          <Plus size={16} /> {t('ws.create')}
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
          className="mb-6 space-y-3 rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
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

      {workspaces.length > 0 && (
        <div className="relative mb-4 max-w-sm">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <Input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder={t('ws.filter')}
            className="pl-9"
            data-testid="ws-filter"
          />
        </div>
      )}

      {(() => {
        const q = filter.trim().toLowerCase()
        const shown = q
          ? workspaces.filter(ws => `${ws.label} ${ws.slug} ${ws.description ?? ''}`.toLowerCase().includes(q))
          : workspaces
        if (workspaces.length === 0) return (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/50 py-16 text-center text-sm text-gray-500">
          {t('ws.empty')}
        </div>
        )
        if (shown.length === 0) return (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/50 py-12 text-center text-sm text-gray-500" data-testid="ws-no-match">
          {t('ws.noMatch', { q: filter.trim() })}
        </div>
        )
        return (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map(ws => (
            <div
              key={ws.slug}
              data-testid={`ws-row-${ws.slug}`}
              role="button"
              tabIndex={0}
              onClick={() => handleSelect(ws)}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSelect(ws) } }}
              className="group relative flex cursor-pointer flex-col rounded-xl border border-gray-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-indigo-300 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              <div className="flex items-start gap-3">
                <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-lg font-semibold text-white ${monogramColor(ws.slug)}`}>
                  {(ws.label || ws.slug).charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-gray-900">{ws.label}</p>
                  <p className="truncate font-mono text-xs text-gray-400">{ws.slug}</p>
                </div>
                {ws.archived_at && (
                  <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500">
                    {t('ws.archivedBadge')}
                  </span>
                )}
              </div>

              {ws.description && (
                <p className="mt-3 line-clamp-2 text-sm text-gray-500">{ws.description}</p>
              )}

              <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-3">
                <span className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 transition-all group-hover:gap-2">
                  {t('ws.select')} <ArrowRight size={15} />
                </span>
                <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                  <button
                    type="button"
                    title={t('ws.archive')}
                    aria-label={t('ws.archive')}
                    onClick={() => archiveMutation.mutate(ws.slug)}
                    disabled={archiveMutation.isPending}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700 disabled:opacity-50"
                  >
                    <Archive size={16} />
                  </button>
                  <button
                    type="button"
                    title={t('common.delete')}
                    aria-label={t('common.delete')}
                    data-testid={`delete-ws-${ws.slug}`}
                    onClick={() => { setDeleteTarget(ws); setDeleteConfirm('') }}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
        )
      })()}

      {deleteTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" data-testid="delete-modal">
          <div className="w-full max-w-sm space-y-4 rounded-xl bg-white p-6 shadow-xl">
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

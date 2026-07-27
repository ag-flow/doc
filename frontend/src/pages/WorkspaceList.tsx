import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Archive, Plus, Trash } from '@phosphor-icons/react'
import { api } from '../lib/api'
import type { WorkspaceOut } from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { relativeDate } from '../lib/relativeDate'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { SectionHead } from '../components/SectionHead'

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
    setSlugError(SLUG_RE.test(v) ? '' : t('ws.slugInvalid'))
  }

  const handleSelect = (ws: WorkspaceOut) => {
    setCurrentSlug(ws.slug)
    navigate(`/ws/${ws.slug}/blocs`)
  }

  const q = filter.trim().toLowerCase()
  const shown = q
    ? workspaces.filter((ws) =>
        `${ws.label} ${ws.slug} ${ws.description ?? ''}`.toLowerCase().includes(q))
    : workspaces

  return (
    <div className="mx-auto max-w-[1000px] px-6 pt-11 pb-24" data-testid="workspace-list">
      <SectionHead kicker={t('ws.kicker')} title={t('ws.title')}>
        {/* Filtre en simple soulignement : un champ encadré ferait boîte. */}
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t('ws.filter')}
          className="w-[220px] rounded-none border-0 border-b border-[var(--color-divider)] bg-transparent pl-0"
          data-testid="ws-filter"
        />
        <Button
          onClick={() => { setSlug(''); setSlugTouched(false); setShowCreate(true) }}
          data-testid="create-ws-btn"
        >
          <Plus size={16} weight="duotone" /> {t('ws.create')}
        </Button>
      </SectionHead>

      <p className="mb-8 max-w-[56ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        {t('ws.chapo')}
      </p>

      <div aria-live="polite">
        {redirectMsg && (
          <p className="mb-5 text-[14px] text-accent-2-700" data-testid="redirect-msg">
            {redirectMsg}
          </p>
        )}
        {apiError && (
          <p className="mb-5 text-[14px] text-accent-2-700" data-testid="api-error">{apiError}</p>
        )}
      </div>

      {showCreate && (
        <form
          data-testid="create-ws-form"
          className="card elev-sm mb-8 max-w-[520px]"
          onSubmit={(e) => { e.preventDefault(); if (!slugError) createMutation.mutate() }}
        >
          <Field label={t('ws.label')} htmlFor="ws-label">
            <Input
              id="ws-label"
              data-testid="label-input"
              value={label}
              onChange={(e) => {
                setLabel(e.target.value)
                if (!slugTouched) {
                  const derived = labelToSlug(e.target.value)
                  setSlug(derived)
                  validateSlug(derived)
                }
              }}
              required
            />
          </Field>
          <Field label={t('ws.slug')} htmlFor="ws-slug" error={slugError || null}>
            <Input
              id="ws-slug"
              data-testid="slug-input"
              value={slug}
              onChange={(e) => { setSlugTouched(true); setSlug(e.target.value); validateSlug(e.target.value) }}
              placeholder="mon-workspace"
              aria-invalid={slugError ? 'true' : undefined}
              required
            />
          </Field>
          <Field label={t('ws.description')} htmlFor="ws-desc">
            <Input id="ws-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
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

      {isLoading ? (
        <p className="text-muted">{t('common.loading')}</p>
      ) : workspaces.length === 0 ? (
        /* État vide : une phrase et le bouton, centrés dans le blanc. */
        <div className="py-24 text-center" data-testid="ws-empty">
          <p className="mb-5 text-[16px] text-ink/[0.6]">{t('ws.empty')}</p>
          <Button onClick={() => setShowCreate(true)}>
            <Plus size={16} weight="duotone" /> {t('ws.create')}
          </Button>
        </div>
      ) : shown.length === 0 ? (
        <p className="py-16 text-center text-[16px] text-ink/[0.6]" data-testid="ws-no-match">
          {t('ws.noMatch', { q: filter.trim() })}
        </p>
      ) : (
        <ul className="m-0 list-none p-0">
          {shown.map((ws, i) => (
            <WorkspaceRow
              key={ws.slug}
              ws={ws}
              index={i + 1}
              onOpen={() => handleSelect(ws)}
              onArchive={() => archiveMutation.mutate(ws.slug)}
              archiving={archiveMutation.isPending}
              onDelete={() => { setDeleteTarget(ws); setDeleteConfirm('') }}
            />
          ))}
        </ul>
      )}

      {deleteTarget && (
        <div className="dialog-backdrop z-50" data-testid="delete-modal">
          <div className="dialog">
            <h4 className="dialog-title">{t('ws.deleteConfirmTitle')}</h4>
            <p className="dialog-body">{t('ws.deleteConfirmMsg', { slug: deleteTarget.slug })}</p>
            <Input
              data-testid="delete-confirm-input"
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              placeholder={deleteTarget.slug}
              autoFocus
            />
            <div className="dialog-actions">
              <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
                {t('common.cancel')}
              </Button>
              <Button
                variant="danger"
                data-testid="confirm-delete-btn"
                disabled={deleteConfirm !== deleteTarget.slug || deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(deleteTarget.slug)}
              >
                {t('ws.deleteConfirm')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Une ligne d'index : numéro, label + slug, description, compteurs. La ligne
 * entière est l'élément cliquable et focusable ; les deux actions de fin de
 * ligne restent des boutons distincts (elles n'ouvrent pas le workspace).
 */
function WorkspaceRow({ ws, index, onOpen, onArchive, archiving, onDelete }: {
  ws: WorkspaceOut
  index: number
  onOpen: () => void
  onArchive: () => void
  archiving: boolean
  onDelete: () => void
}) {
  const { t } = useTranslation()
  const counts = [
    t('ws.blocksCount', { count: ws.blocks_count }),
    t('ws.docsCount', { count: ws.documents_count }),
  ].join(' · ')

  return (
    <li className="group relative border-b border-[var(--color-divider)]">
      <button
        type="button"
        onClick={onOpen}
        data-testid={`ws-row-${ws.slug}`}
        className={`grid w-full grid-cols-[36px_1fr] items-baseline gap-5 px-1 py-4 text-left
          transition-colors hover:bg-ink/[0.04] sm:grid-cols-[36px_1fr_260px_130px]
          ${ws.archived_at ? 'opacity-50' : ''}`}
      >
        <span className="text-right text-[15px] font-[600] text-ink/[0.38] [font-family:var(--font-heading)]">
          {String(index).padStart(2, '0')}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[22px] font-[600] [font-family:var(--font-heading)]">
            {ws.label}
            {ws.archived_at && (
              <span className="tag tag-neutral ml-2.5 align-middle">{t('ws.archivedBadge')}</span>
            )}
          </span>
          <span className="mt-0.5 block text-[12px] tracking-[0.04em] text-accent-700">
            {ws.slug}
          </span>
        </span>
        <span className="hidden truncate text-[14px] text-ink/[0.62] sm:block">
          {ws.description}
        </span>
        <span className="hidden text-right text-[13px] text-ink/[0.5] sm:block">
          {counts}
          <span className="block text-[12px] text-ink/[0.4]">
            {ws.last_activity_at ? relativeDate(ws.last_activity_at) : t('ws.noActivity')}
          </span>
        </span>
      </button>

      {/* Actions révélées au survol ou au focus clavier — jamais cachées au
          clavier, sinon elles deviennent inatteignables. */}
      <span
        className="absolute right-1 top-1/2 flex -translate-y-1/2 gap-1 opacity-0
          transition-opacity focus-within:opacity-100 group-hover:opacity-100"
      >
        <Button
          variant="icon"
          size="sm"
          title={t('ws.archive')}
          aria-label={`${t('ws.archive')} ${ws.label}`}
          onClick={onArchive}
          disabled={archiving}
        >
          <Archive size={16} weight="duotone" />
        </Button>
        <Button
          variant="icon"
          size="sm"
          title={t('common.delete')}
          aria-label={`${t('common.delete')} ${ws.label}`}
          data-testid={`delete-ws-${ws.slug}`}
          onClick={onDelete}
          className="text-accent-2-700"
        >
          <Trash size={16} weight="duotone" />
        </Button>
      </span>
    </li>
  )
}

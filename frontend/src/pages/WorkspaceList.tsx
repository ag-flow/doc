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
import { EmptyState, ErrorLine, TableSkeleton } from '../components/ui/states'
import { ConfirmDialog } from '../components/ConfirmDialog'

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

      <ErrorLine message={redirectMsg} testId="redirect-msg" />
      <ErrorLine message={apiError} testId="api-error" />

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
        <TableSkeleton rows={5} columns={4} />
      ) : workspaces.length === 0 ? (
        <EmptyState
          testId="ws-empty"
          message={t('ws.empty')}
          action={
            <Button onClick={() => setShowCreate(true)}>
              <Plus size={16} weight="duotone" /> {t('ws.create')}
            </Button>
          }
        />
      ) : shown.length === 0 ? (
        <EmptyState testId="ws-no-match" message={t('ws.noMatch', { q: filter.trim() })} />
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
        <ConfirmDialog
          testId="delete-modal"
          title={t('ws.deleteConfirmTitle')}
          message={
            <>
              <p className="m-0">{t('ws.deleteConfirmMsg', { slug: deleteTarget.slug })}</p>
              <Input
                data-testid="delete-confirm-input"
                className="mt-3"
                value={deleteConfirm}
                onChange={(e) => setDeleteConfirm(e.target.value)}
                placeholder={deleteTarget.slug}
                autoFocus
              />
            </>
          }
          impactMessage={t('ws.deleteImpact', {
            docs: deleteTarget.documents_count,
            blocks: deleteTarget.blocks_count,
          })}
          confirmLabel={t('ws.deleteConfirm')}
          confirmTestId="confirm-delete-btn"
          pending={deleteMutation.isPending}
          // Garde de saisie : le bouton reste verrouillé tant que le slug exact
          // n'est pas retapé — on ne détruit pas un workspace par inadvertance.
          confirmDisabled={deleteConfirm !== deleteTarget.slug}
          onConfirm={() => deleteMutation.mutate(deleteTarget.slug)}
          onCancel={() => setDeleteTarget(null)}
        />
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

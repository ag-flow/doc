import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, ArrowRight, ChevronDown, ChevronRight, Eye, EyeOff, Trash2 } from 'lucide-react'
import {
  api, ApiError, docsApi, referencesApi,
  type BrokenLinkBloc, type BrokenLinkDetail, type DataBlockOut, type FunctionalType,
} from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { DeleteBlocDialog } from '../components/DeleteBlocDialog'

const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/

const MONOGRAM_COLORS = [
  'bg-indigo-500', 'bg-emerald-500', 'bg-rose-500', 'bg-amber-500',
  'bg-sky-500', 'bg-violet-500', 'bg-teal-500', 'bg-fuchsia-500',
]
function monogramColor(slug: string): string {
  let h = 0
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) >>> 0
  return MONOGRAM_COLORS[h % MONOGRAM_COLORS.length]
}

// ── Badge + détail des liens cassés par bloc ──────────────────────────────────

function BrokenLinksDetail({ wsSlug, blocId }: { wsSlug: string; blocId: string }) {
  const { data: details = [], isLoading } = useQuery<BrokenLinkDetail[]>({
    queryKey: ['broken-links-detail', wsSlug, blocId],
    queryFn: () => referencesApi.getBrokenLinksDetail(wsSlug, blocId),
    staleTime: 30_000,
  })

  if (isLoading) return <p className="text-xs text-gray-400 px-2 py-1">Chargement…</p>
  if (details.length === 0) return null

  return (
    <div className="mt-1 ml-2 border-l-2 border-amber-200 pl-3 space-y-1">
      {details.map((d) => (
        <p key={`${d.source_ref}-${d.target_label}`} className="text-xs text-gray-600">
          <span className="font-medium">{d.source_title}</span>
          {' → '}
          <span className="text-amber-700">« {d.target_label} »</span>
          <span className="text-gray-400"> (cible supprimée)</span>
        </p>
      ))}
    </div>
  )
}

function BrokenLinksBadge({
  wsSlug,
  blocId,
  count,
}: {
  wsSlug: string
  blocId: string
  count: number
}) {
  const [open, setOpen] = useState(false)

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded px-2 py-1 text-xs font-medium
                   bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors"
        title="Voir les liens cassés"
      >
        <AlertTriangle size={12} />
        {count} doc{count > 1 ? 's' : ''} avec liens cassés
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
      </button>
      {open && <BrokenLinksDetail wsSlug={wsSlug} blocId={blocId} />}
    </div>
  )
}

function BlocsTable({ blocs, wsSlug }: { blocs: DataBlockOut[]; wsSlug: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [blocToDelete, setBlocToDelete] = useState<DataBlockOut | null>(null)

  const exposeMutation = useMutation({
    mutationFn: ({ slug, exposed }: { slug: string; exposed: boolean }) =>
      docsApi.setBlockExposed(wsSlug, slug, exposed),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['blocs', wsSlug] })
    },
  })

  function handleDeleted() {
    // Le bloc et ses documents ont disparu : rafraîchir la liste ET les liens
    // cassés (des références entrantes peuvent être devenues orphelines).
    void qc.invalidateQueries({ queryKey: ['blocs', wsSlug] })
    void qc.invalidateQueries({ queryKey: ['broken-links', wsSlug] })
    setBlocToDelete(null)
  }

  const { data: brokenLinks = [] } = useQuery<BrokenLinkBloc[]>({
    queryKey: ['broken-links', wsSlug],
    queryFn: () => referencesApi.getBrokenLinks(wsSlug),
    staleTime: 60_000,
  })

  // index par bloc id → count
  const brokenByBloc = Object.fromEntries(
    brokenLinks.map((b) => [b.bloc ?? '', b.docs_with_broken_links])
  )

  return (
    <>
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {blocs.map((bloc) => {
        const brokenCount = bloc.id ? (brokenByBloc[bloc.id] ?? 0) : 0
        return (
          <div
            key={bloc.slug}
            data-testid={`bloc-row-${bloc.slug}`}
            className="flex flex-col rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-all hover:border-indigo-300 hover:shadow-md"
          >
            <div className="flex items-start gap-3">
              <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-lg font-semibold text-white ${monogramColor(bloc.slug)}`}>
                {(bloc.label || bloc.slug).charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-gray-900">{bloc.label}</p>
                <p className="truncate font-mono text-xs text-gray-400">{bloc.slug}</p>
              </div>
              <button
                type="button"
                title={bloc.exposed ? 'Rendre privé' : 'Exposer publiquement'}
                onClick={() => exposeMutation.mutate({ slug: bloc.slug, exposed: !bloc.exposed })}
                disabled={exposeMutation.isPending}
                className={`flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors ${
                  bloc.exposed
                    ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                }`}
                data-testid={`expose-bloc-${bloc.slug}`}
              >
                {bloc.exposed ? <Eye size={11} /> : <EyeOff size={11} />}
                {bloc.exposed ? 'Public' : 'Privé'}
              </button>
            </div>

            <div className="mt-3">
              <span className="inline-flex items-center rounded bg-gray-50 px-2 py-0.5 font-mono text-[11px] text-gray-500">
                {bloc.functional_type_slug}
              </span>
            </div>

            {brokenCount > 0 && bloc.id && (
              <div className="mt-2">
                <BrokenLinksBadge wsSlug={wsSlug} blocId={bloc.id} count={brokenCount} />
              </div>
            )}

            <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-3">
              <button
                type="button"
                onClick={() => void navigate(`/ws/${wsSlug}/blocs/${bloc.slug}/documents`)}
                className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:gap-2 transition-all"
                data-testid={`open-bloc-${bloc.slug}`}
              >
                {t('blocs.open')} <ArrowRight size={15} />
              </button>
              <button
                type="button"
                title={t('blocs.delete')}
                aria-label={t('blocs.delete')}
                onClick={() => setBlocToDelete(bloc)}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600"
                data-testid={`delete-bloc-${bloc.slug}`}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </div>
        )
      })}
    </div>
    {blocToDelete && (
      <DeleteBlocDialog
        wsSlug={wsSlug}
        blockSlug={blocToDelete.slug}
        blockLabel={blocToDelete.label}
        onClose={() => setBlocToDelete(null)}
        onDeleted={handleDeleted}
      />
    )}
    </>
  )
}

export function BlocsAdmin() {
  const { t } = useTranslation()
  const { wsSlug } = useParams<{ wsSlug: string }>()
  const qc = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [slug, setSlug] = useState('')
  const [label, setLabel] = useState('')
  const [typeSlug, setTypeSlug] = useState('')
  const [slugError, setSlugError] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [apiError, setApiError] = useState('')

  const { data: blocs = [], isLoading } = useQuery<DataBlockOut[]>({
    queryKey: ['blocs', wsSlug],
    queryFn: () => docsApi.getBlocks(wsSlug!),
    enabled: Boolean(wsSlug),
  })

  const { data: types = [] } = useQuery<FunctionalType[]>({
    queryKey: ['types', wsSlug],
    queryFn: () => api.get<FunctionalType[]>(`/workspaces/${wsSlug}/types`),
    enabled: Boolean(wsSlug),
  })

  // Types racines uniquement (sans parent), groupés par template d'origine
  // (templates triés, types créés à la main en dernier).
  const rootTypeGroups = (() => {
    const byTemplate = new Map<string | null, FunctionalType[]>()
    for (const tp of types.filter((ty) => !ty.parent_slug)) {
      byTemplate.set(tp.source_template, [...(byTemplate.get(tp.source_template) ?? []), tp])
    }
    for (const list of byTemplate.values()) list.sort((a, b) => a.label.localeCompare(b.label))
    const templates = [...byTemplate.keys()]
      .filter((k): k is string => k !== null)
      .sort((a, b) => a.localeCompare(b))
    const groups = templates.map((tpl) => ({ template: tpl as string | null, types: byTemplate.get(tpl)! }))
    const manual = byTemplate.get(null)
    if (manual) groups.push({ template: null, types: manual })
    return groups
  })()

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<DataBlockOut>(`/workspaces/${wsSlug}/blocks`, {
        slug,
        label,
        functional_type_slug: typeSlug,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['blocs', wsSlug] })
      setShowCreate(false)
      setSlug('')
      setLabel('')
      setTypeSlug('')
      setSlugTouched(false)
      setApiError('')
    },
    onError: (e: Error) => setApiError(e.message),
  })

  const validateSlug = (v: string) => {
    if (!SLUG_RE.test(v)) setSlugError(t('ws.slugInvalid'))
    else setSlugError('')
  }

  const canSubmit = !slugError && slug && label && typeSlug && !createMutation.isPending

  if (isLoading) return <div className="p-8">{t('common.loading')}</div>

  function handleExport() {
    setApiError('')
    void api.getBlob(`/workspaces/${wsSlug}/export?scope=workspace`)
      .then((blob) => {
        const blobUrl = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = blobUrl
        a.download = `${wsSlug}.zip`
        a.click()
        URL.revokeObjectURL(blobUrl)
      })
      .catch((e) => setApiError(e instanceof ApiError ? e.message : t('error.generic')))
  }

  return (
    <div className="mx-auto max-w-3xl p-8" data-testid="blocs-admin">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">{t('blocs.title')}</h1>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={handleExport} data-testid="export-workspace-btn">
            {t('blocs.export', 'Exporter (markdown)')}
          </Button>
          <Button onClick={() => setShowCreate(true)} data-testid="create-bloc-btn">
            {t('blocs.create')}
          </Button>
        </div>
      </div>

      {apiError && (
        <p className="mb-4 text-sm text-red-600" data-testid="api-error">
          {apiError}
        </p>
      )}

      {showCreate && (
        <form
          data-testid="create-bloc-form"
          className="mb-6 space-y-3 rounded border border-gray-200 bg-white p-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (canSubmit) createMutation.mutate()
          }}
        >
          <div>
            <label className="mb-1 block text-sm font-medium">{t('ws.label')}</label>
            <Input
              data-testid="bloc-label-input"
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
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">{t('ws.slug')}</label>
            <Input
              data-testid="bloc-slug-input"
              value={slug}
              onChange={(e) => {
                setSlugTouched(true)
                setSlug(e.target.value)
                validateSlug(e.target.value)
              }}
              placeholder="mon-bloc"
              required
            />
            {slugError && <p className="mt-1 text-xs text-red-500">{slugError}</p>}
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">{t('blocs.rootType')}</label>
            <select
              data-testid="bloc-type-select"
              className="block w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={typeSlug}
              onChange={(e) => setTypeSlug(e.target.value)}
              required
            >
              <option value="">{t('blocs.selectType')}</option>
              {rootTypeGroups.map((group) => (
                <optgroup
                  key={group.template ?? '__manual__'}
                  label={
                    group.template !== null
                      ? t('types.templateGroup', { template: group.template })
                      : t('types.manualGroup')
                  }
                >
                  {group.types.map((tp) => (
                    <option key={tp.slug} value={tp.slug}>
                      {tp.label} ({tp.slug})
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={!canSubmit}>
              {t('common.save')}
            </Button>
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                setShowCreate(false)
                setApiError('')
              }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      )}

      {blocs.length === 0 ? (
        <p className="text-gray-500" data-testid="no-blocs">
          {t('blocs.empty')}
        </p>
      ) : (
        <BlocsTable blocs={blocs} wsSlug={wsSlug!} />
      )}
    </div>
  )
}

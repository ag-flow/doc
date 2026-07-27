import { useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation, Trans } from 'react-i18next'
import { ArrowRight, CaretDown, CaretRight, Export, Eye, EyeSlash, PencilSimple, Plus, Trash } from '@phosphor-icons/react'
import {
  api, ApiError, docsApi, referencesApi,
  type BrokenLinkBloc, type BrokenLinkDetail, type DataBlockOut, type FunctionalType,
} from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { relativeDate } from '../lib/relativeDate'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { SectionHead } from '../components/SectionHead'
import { DeleteBlocDialog } from '../components/DeleteBlocDialog'

const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/

/** Blocs ordonnés en arbre : chaque bloc suit son parent, avec sa profondeur.
 *  La hiérarchie se lit par l'indentation, pas par des filets. */
function orderByHierarchy(blocs: DataBlockOut[]): { bloc: DataBlockOut; depth: number }[] {
  const bySlug = new Map(blocs.map((b) => [b.slug, b]))
  const children = new Map<string | null, DataBlockOut[]>()
  for (const b of blocs) {
    // Un parent hors liste (jamais en pratique) est traité comme une racine.
    const key = b.parent_slug && bySlug.has(b.parent_slug) ? b.parent_slug : null
    children.set(key, [...(children.get(key) ?? []), b])
  }
  const out: { bloc: DataBlockOut; depth: number }[] = []
  const walk = (parent: string | null, depth: number) => {
    for (const b of children.get(parent) ?? []) {
      out.push({ bloc: b, depth })
      walk(b.slug, depth + 1)
    }
  }
  walk(null, 0)
  return out
}

// ── Liens cassés ──────────────────────────────────────────────────────────────

function BrokenLinksDetail({ wsSlug, blocId }: { wsSlug: string; blocId: string }) {
  const { t } = useTranslation()
  const { data: details = [], isLoading } = useQuery<BrokenLinkDetail[]>({
    queryKey: ['broken-links-detail', wsSlug, blocId],
    queryFn: () => referencesApi.getBrokenLinksDetail(wsSlug, blocId),
    staleTime: 30_000,
  })

  if (isLoading) return <p className="text-muted text-[12px]">{t('common.loading')}</p>
  if (details.length === 0) return null

  return (
    <ul className="m-0 list-none space-y-1 p-0 pt-1.5">
      {details.map((d) => (
        <li key={`${d.source_ref}-${d.target_label}`} className="text-[12px] text-ink/[0.7]">
          <span className="[font-family:var(--font-heading)] font-[600]">{d.source_title}</span>
          {' → '}
          <span className="text-accent-2-700">« {d.target_label} »</span>{' '}
          <span className="text-muted">{t('blocs.brokenTargetGone')}</span>
        </li>
      ))}
    </ul>
  )
}

/** Compteur de liens cassés : gris à zéro, magenta dès qu'il y en a — c'est le
 *  seul emploi du second accent sur cet écran. */
function BrokenLinksCell({ wsSlug, blocId, count }: {
  wsSlug: string
  blocId: string
  count: number
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  if (count === 0) return <span className="text-muted">0</span>

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={t('blocs.brokenDetail')}
        className="inline-flex items-center gap-1 border-0 bg-transparent p-0 text-[14px] text-accent-2-700 hover:underline"
        data-testid={`broken-links-${blocId}`}
      >
        {count}
        {open ? <CaretDown size={11} weight="duotone" /> : <CaretRight size={11} weight="duotone" />}
      </button>
      {open && <BrokenLinksDetail wsSlug={wsSlug} blocId={blocId} />}
    </>
  )
}

// ── Table des blocs ───────────────────────────────────────────────────────────

function BlocsTable({ blocs, wsSlug }: { blocs: DataBlockOut[]; wsSlug: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [blocToDelete, setBlocToDelete] = useState<DataBlockOut | null>(null)
  const [editing, setEditing] = useState<DataBlockOut | null>(null)

  const exposeMutation = useMutation({
    mutationFn: ({ slug, exposed }: { slug: string; exposed: boolean }) =>
      docsApi.setBlockExposed(wsSlug, slug, exposed),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['blocs', wsSlug] }) },
  })

  const renameMutation = useMutation({
    mutationFn: ({ slug, label }: { slug: string; label: string }) =>
      docsApi.updateBlock(wsSlug, slug, { label }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['blocs', wsSlug] })
      setEditing(null)
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
  const brokenByBloc = Object.fromEntries(
    brokenLinks.map((b) => [b.bloc ?? '', b.docs_with_broken_links]),
  )

  const open = (slug: string) => void navigate(`/ws/${wsSlug}/blocs/${slug}/documents`)

  return (
    <>
      <table className="table" data-testid="blocs-table">
        <thead>
          <tr>
            <th>{t('blocs.colBloc')}</th>
            <th>{t('blocs.colSlug')}</th>
            <th>{t('blocs.colType')}</th>
            <th>{t('blocs.colDocs')}</th>
            <th>{t('blocs.colBroken')}</th>
            <th>{t('blocs.colLastWrite')}</th>
            <th>{t('blocs.colExposed')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {orderByHierarchy(blocs).map(({ bloc, depth }) => (
            <tr key={bloc.slug} data-testid={`bloc-row-${bloc.slug}`}>
              <td
                className="[font-family:var(--font-heading)] text-[16px] font-[600]"
                style={{ paddingLeft: `calc(var(--space-2) + ${depth} * var(--space-4))` }}
                data-depth={depth}
              >
                <button
                  type="button"
                  onClick={() => open(bloc.slug)}
                  className="border-0 bg-transparent p-0 text-left font-inherit"
                  data-testid={`open-bloc-${bloc.slug}`}
                >
                  {bloc.label}
                </button>
              </td>
              <td className="text-accent-700">{bloc.slug}</td>
              <td><span className="tag tag-accent">{bloc.functional_type_slug}</span></td>
              <td>{bloc.documents_count}</td>
              <td>
                <BrokenLinksCell
                  wsSlug={wsSlug}
                  blocId={bloc.id}
                  count={brokenByBloc[bloc.id] ?? 0}
                />
              </td>
              <td className="text-ink/[0.55]">
                {bloc.last_write_at ? relativeDate(bloc.last_write_at) : t('blocs.noWrite')}
              </td>
              <td>
                {/* Le drapeau se change sans quitter la liste. */}
                <button
                  type="button"
                  onClick={() => exposeMutation.mutate({ slug: bloc.slug, exposed: !bloc.exposed })}
                  disabled={exposeMutation.isPending}
                  title={bloc.exposed ? t('blocs.makePrivate') : t('blocs.makePublic')}
                  className="border-0 bg-transparent p-0"
                  data-testid={`expose-bloc-${bloc.slug}`}
                >
                  <span className={`tag ${bloc.exposed ? 'tag-accent' : 'tag-neutral'} gap-1`}>
                    {bloc.exposed
                      ? <Eye size={11} weight="duotone" />
                      : <EyeSlash size={11} weight="duotone" />}
                    {bloc.exposed ? t('blocs.public') : t('blocs.private')}
                  </span>
                </button>
              </td>
              <td className="whitespace-nowrap text-right">
                <Button variant="icon" size="sm" title={t('blocs.open')}
                  aria-label={`${t('blocs.open')} ${bloc.label}`} onClick={() => open(bloc.slug)}>
                  <ArrowRight size={15} weight="duotone" />
                </Button>
                <Button variant="icon" size="sm" title={t('blocs.edit')}
                  aria-label={`${t('blocs.edit')} ${bloc.label}`}
                  data-testid={`edit-bloc-${bloc.slug}`} onClick={() => setEditing(bloc)}>
                  <PencilSimple size={15} weight="duotone" />
                </Button>
                <Button variant="icon" size="sm" title={t('blocs.delete')}
                  aria-label={`${t('blocs.delete')} ${bloc.label}`} className="text-accent-2-700"
                  data-testid={`delete-bloc-${bloc.slug}`} onClick={() => setBlocToDelete(bloc)}>
                  <Trash size={15} weight="duotone" />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {editing && (
        <div className="dialog-backdrop z-50" data-testid="edit-bloc-dialog">
          <form
            className="dialog"
            onSubmit={(e) => {
              e.preventDefault()
              const label = new FormData(e.currentTarget).get('label')
              if (typeof label === 'string' && label.trim()) {
                renameMutation.mutate({ slug: editing.slug, label: label.trim() })
              }
            }}
          >
            <h4 className="dialog-title">{t('blocs.editTitle')}</h4>
            <Field label={t('ws.label')} htmlFor="edit-bloc-label">
              <Input id="edit-bloc-label" name="label" defaultValue={editing.label} autoFocus required />
            </Field>
            <div className="dialog-actions">
              <Button variant="secondary" type="button" onClick={() => setEditing(null)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={renameMutation.isPending}>{t('common.save')}</Button>
            </div>
          </form>
        </div>
      )}

      {blocToDelete && (
        <DeleteBlocDialog
          wsSlug={wsSlug}
          blockSlug={blocToDelete.slug}
          blockLabel={blocToDelete.label}
          documentsCount={blocToDelete.documents_count}
          onClose={() => setBlocToDelete(null)}
          onDeleted={handleDeleted}
        />
      )}
    </>
  )
}

// ── Écran ─────────────────────────────────────────────────────────────────────

export function BlocsAdmin() {
  const { t } = useTranslation()
  const { wsSlug } = useParams<{ wsSlug: string }>()
  const qc = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [slug, setSlug] = useState('')
  const [label, setLabel] = useState('')
  const [typeSlug, setTypeSlug] = useState('')
  const [parentSlug, setParentSlug] = useState('')
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

  // Sans bloc parent, le type doit être racine (contrainte miroir I-5) ; avec un
  // parent, le type proposé doit être un fils du type du parent.
  const parent = blocs.find((b) => b.slug === parentSlug) ?? null
  const parentType = parent ? types.find((ty) => ty.slug === parent.functional_type_slug) : null
  const selectableTypes = parent
    ? types.filter((ty) => ty.parent_slug === parentType?.slug)
    : types.filter((ty) => !ty.parent_slug)

  const typeGroups = (() => {
    const byTemplate = new Map<string | null, FunctionalType[]>()
    for (const tp of selectableTypes) {
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
        parent_slug: parentSlug || null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['blocs', wsSlug] })
      setShowCreate(false)
      setSlug('')
      setLabel('')
      setTypeSlug('')
      setParentSlug('')
      setSlugTouched(false)
      setApiError('')
    },
    onError: (e: Error) => setApiError(e.message),
  })

  const validateSlug = (v: string) => {
    setSlugError(SLUG_RE.test(v) ? '' : t('ws.slugInvalid'))
  }

  const canSubmit = !slugError && slug && label && typeSlug && !createMutation.isPending

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
    <div className="mx-auto max-w-[1000px] px-6 pt-11 pb-24" data-testid="blocs-admin">
      <SectionHead kicker={wsSlug ?? ''} title={t('blocs.title')}>
        <Button variant="secondary" onClick={handleExport} data-testid="export-workspace-btn">
          <Export size={16} weight="duotone" /> {t('blocs.export', 'Exporter (markdown)')}
        </Button>
        <Button onClick={() => setShowCreate(true)} data-testid="create-bloc-btn">
          <Plus size={16} weight="duotone" /> {t('blocs.create')}
        </Button>
      </SectionHead>

      <p className="mb-8 max-w-[56ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        <Trans
          i18nKey="blocs.chapo"
          components={[<span key="0" />, <Link key="1" to={`/ws/${wsSlug}/types`} />]}
        />
      </p>

      <div aria-live="polite">
        {apiError && (
          <p className="mb-5 text-[14px] text-accent-2-700" data-testid="api-error">{apiError}</p>
        )}
      </div>

      {showCreate && (
        <form
          data-testid="create-bloc-form"
          className="card elev-sm mb-8 max-w-[520px]"
          onSubmit={(e) => { e.preventDefault(); if (canSubmit) createMutation.mutate() }}
        >
          <Field label={t('ws.label')} htmlFor="bloc-label">
            <Input
              id="bloc-label"
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
          </Field>
          <Field label={t('ws.slug')} htmlFor="bloc-slug" error={slugError || null}>
            <Input
              id="bloc-slug"
              data-testid="bloc-slug-input"
              value={slug}
              onChange={(e) => { setSlugTouched(true); setSlug(e.target.value); validateSlug(e.target.value) }}
              placeholder="mon-bloc"
              aria-invalid={slugError ? 'true' : undefined}
              required
            />
          </Field>
          <Field label={t('blocs.parent')} htmlFor="bloc-parent">
            <select
              id="bloc-parent"
              className="input"
              value={parentSlug}
              onChange={(e) => { setParentSlug(e.target.value); setTypeSlug('') }}
              data-testid="bloc-parent-select"
            >
              <option value="">{t('blocs.noParent')}</option>
              {blocs.map((b) => (
                <option key={b.slug} value={b.slug}>{b.label}</option>
              ))}
            </select>
          </Field>
          <Field label={t('blocs.rootType')} htmlFor="bloc-type">
            <select
              id="bloc-type"
              data-testid="bloc-type-select"
              className="input"
              value={typeSlug}
              onChange={(e) => setTypeSlug(e.target.value)}
              required
            >
              <option value="">{t('blocs.selectType')}</option>
              {typeGroups.map((group) => (
                <optgroup
                  key={group.template ?? '__manual__'}
                  label={
                    group.template !== null
                      ? t('types.templateGroup', { template: group.template })
                      : t('types.manualGroup')
                  }
                >
                  {group.types.map((tp) => (
                    <option key={tp.slug} value={tp.slug}>{tp.label} ({tp.slug})</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </Field>
          <div className="flex gap-2">
            <Button type="submit" disabled={!canSubmit}>{t('common.save')}</Button>
            <Button
              variant="secondary"
              type="button"
              onClick={() => { setShowCreate(false); setApiError('') }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      )}

      {isLoading ? (
        <p className="text-muted">{t('common.loading')}</p>
      ) : blocs.length === 0 ? (
        <div className="py-24 text-center" data-testid="no-blocs">
          <p className="mb-5 text-[16px] text-ink/[0.6]">{t('blocs.empty')}</p>
          <Button onClick={() => setShowCreate(true)}>
            <Plus size={16} weight="duotone" /> {t('blocs.create')}
          </Button>
        </div>
      ) : (
        <BlocsTable blocs={blocs} wsSlug={wsSlug!} />
      )}
    </div>
  )
}

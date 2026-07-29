import { Fragment, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { CaretDown, CaretRight, Package, Plus, Trash } from '@phosphor-icons/react'
import { api } from '../lib/api'
import type { FunctionalTypeRich, TemplateInfo } from '../lib/api'
import { labelToSlug } from '../lib/slug'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { SectionHead } from '../components/SectionHead'
import { EmptyState, ErrorLine, TableSkeleton } from '../components/ui/states'
import { TypePropertiesPanel } from '../components/TypePropertiesPanel'

interface TypeNode {
  type: FunctionalTypeRich
  depth: number
}

/** Aplati la hiérarchie en ordre d'arbre : racines triées par libellé, puis
 *  leurs enfants récursivement. Un parent inconnu (incohérence de données) est
 *  traité comme racine plutôt que masqué. */
export function flattenTypeTree(types: FunctionalTypeRich[]): TypeNode[] {
  const slugs = new Set(types.map((ty) => ty.slug))
  const byParent = new Map<string | null, FunctionalTypeRich[]>()
  for (const ty of types) {
    const key = ty.parent_slug !== null && slugs.has(ty.parent_slug) ? ty.parent_slug : null
    byParent.set(key, [...(byParent.get(key) ?? []), ty])
  }
  const out: TypeNode[] = []
  const visited = new Set<string>()
  const visit = (parent: string | null, depth: number) => {
    const children = [...(byParent.get(parent) ?? [])].sort((a, b) =>
      a.label.localeCompare(b.label),
    )
    for (const ty of children) {
      if (visited.has(ty.slug)) continue
      visited.add(ty.slug)
      out.push({ type: ty, depth })
      visit(ty.slug, depth + 1)
    }
  }
  visit(null, 0)
  // Garde-fou cycle parent : tout type jamais atteint est ajouté en racine.
  for (const ty of types) {
    if (!visited.has(ty.slug)) out.push({ type: ty, depth: 0 })
  }
  return out
}

interface TypeGroup {
  /** Slug du template d'origine ; null = types créés à la main. */
  template: string | null
  nodes: TypeNode[]
}

/** Regroupe l'arbre par template d'origine de chaque racine (un descendant suit
 *  sa racine, même si sa propre provenance diffère). Templates triés par slug,
 *  groupe « à la main » en dernier. */
export function groupTypeTree(types: FunctionalTypeRich[]): TypeGroup[] {
  const byTemplate = new Map<string | null, TypeNode[]>()
  let current: string | null = null
  for (const node of flattenTypeTree(types)) {
    if (node.depth === 0) current = node.type.source_template
    byTemplate.set(current, [...(byTemplate.get(current) ?? []), node])
  }
  const templates = [...byTemplate.keys()]
    .filter((k): k is string => k !== null)
    .sort((a, b) => a.localeCompare(b))
  const groups: TypeGroup[] = templates.map((tpl) => ({
    template: tpl,
    nodes: byTemplate.get(tpl)!,
  }))
  const manual = byTemplate.get(null)
  if (manual) groups.push({ template: null, nodes: manual })
  return groups
}

export function TypesAdmin() {
  const { t } = useTranslation()
  // Route sous /ws/:wsSlug/types — le paramètre s'appelle wsSlug
  const { wsSlug: ws } = useParams<{ wsSlug: string }>()
  const queryClient = useQueryClient()

  const [creating, setCreating] = useState(false)
  const [newSlug, setNewSlug] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newParent, setNewParent] = useState('')
  const [newInherit, setNewInherit] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const [showImport, setShowImport] = useState(false)
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [importMsg, setImportMsg] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [expandedType, setExpandedType] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // Fermeture du panneau d'édition en place par Échap (en plus du bouton et du reclic).
  useEffect(() => {
    if (expandedType === null) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpandedType(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expandedType])

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
    mutationFn: (body: { slug: string; label: string; parent_slug?: string; inherit_slug?: string }) =>
      api.post<FunctionalTypeRich>(`/workspaces/${ws}/types`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['types-rich', ws] })
      setCreating(false)
      setNewSlug('')
      setNewLabel('')
      setNewParent('')
      setNewInherit('')
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
    createMutation.mutate({
      slug: newSlug,
      label: newLabel,
      parent_slug: newParent || undefined,
      inherit_slug: newInherit || undefined,
    })
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

  const nodes = groupTypeTree(types)

  return (
    <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
      <SectionHead kicker={ws ?? ''} title={t('types.title')}>
        <Button variant="secondary" onClick={openImportModal} data-testid="import-template-btn">
          {t('tpl.importFromTemplate')}
        </Button>
        <Button onClick={() => setCreating((v) => !v)} data-testid="create-type-btn">
          <Plus size={15} weight="duotone" /> {t('types.create')}
        </Button>
      </SectionHead>

      <p className="mb-8 max-w-[56ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        {t('types.chapo')}
      </p>

      {creating && (
        <form
          className="card elev-sm mb-8"
          onSubmit={(e) => { e.preventDefault(); handleCreate() }}
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label={t('types.label')} htmlFor="type-label">
              <Input
                id="type-label"
                value={newLabel}
                onChange={(e) => {
                  setNewLabel(e.target.value)
                  if (!slugTouched) setNewSlug(labelToSlug(e.target.value))
                }}
                placeholder="Mon type"
                data-testid="label-input"
              />
            </Field>
            <Field label={t('types.slug')} htmlFor="type-slug">
              <Input
                id="type-slug"
                value={newSlug}
                onChange={(e) => { setSlugTouched(true); setNewSlug(e.target.value) }}
                placeholder="mon-type"
                data-testid="slug-input"
              />
            </Field>
            <Field label={t('types.parent')} htmlFor="type-parent">
              <select
                id="type-parent"
                className="input"
                value={newParent}
                onChange={(e) => setNewParent(e.target.value)}
                data-testid="parent-select"
              >
                <option value="">{t('types.none')}</option>
                {flattenTypeTree(types).map(({ type: ty, depth }) => (
                  <option key={ty.slug} value={ty.slug}>
                    {'\u00a0'.repeat(depth * 3) + ty.label}
                  </option>
                ))}
              </select>
            </Field>
            {/* Héritage = copie des propriétés du type choisi À LA CRÉATION
                (même sémantique que `inherit:` des templates) — pas de lien
                vivant, les évolutions du type source ne se propagent pas. */}
            <Field label={t('types.inherit')} htmlFor="type-inherit">
              <select
                id="type-inherit"
                className="input"
                value={newInherit}
                onChange={(e) => setNewInherit(e.target.value)}
                title={t('types.inheritHint')}
                data-testid="inherit-select"
              >
                <option value="">{t('types.none')}</option>
                {flattenTypeTree(types).map(({ type: ty, depth }) => (
                  <option key={ty.slug} value={ty.slug}>
                    {'\u00a0'.repeat(depth * 3) + ty.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <ErrorLine message={formError} testId="type-form-error" />
          <div className="flex gap-2">
            <Button type="submit" disabled={createMutation.isPending}>
              {t('types.save')}
            </Button>
            <Button variant="secondary" type="button" onClick={() => setCreating(false)}>
              {t('types.cancel')}
            </Button>
          </div>
        </form>
      )}

      {isLoading ? (
        <TableSkeleton rows={5} columns={5} testId="types-skeleton" />
      ) : types.length === 0 ? (
        <EmptyState
          testId="types-empty"
          message={t('types.empty', 'Aucun type fonctionnel — créez-en un ou importez un template.')}
          action={
            <Button onClick={() => setCreating(true)}>
              <Plus size={15} weight="duotone" /> {t('types.create')}
            </Button>
          }
        />
      ) : (
      <table className="table" data-testid="types-table">
        <thead>
          <tr>
            <th>{t('types.label')}</th>
            <th>{t('types.slug')}</th>
            <th>{t('types.parent')}</th>
            <th>{t('types.colProps')}</th>
            <th>{t('types.colDocs')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {nodes.map((group) => (
            <Fragment key={group.template ?? '__manual__'}>
              <tr data-testid={`type-group-${group.template ?? 'manual'}`}>
                <td colSpan={6} className="border-b-0 pt-5 pb-1">
                  <h6 className="m-0 flex items-center gap-1.5 text-ink/[0.5]">
                    {group.template !== null ? (
                      <>
                        <Package size={13} weight="duotone" className="text-accent-700" />
                        {t('types.templateGroup', { template: group.template })}
                      </>
                    ) : (
                      t('types.manualGroup')
                    )}
                  </h6>
                </td>
              </tr>
              {group.nodes.map(({ type, depth }) => (
                <Fragment key={type.slug}>
                  {/* Clic sur la ligne = édition en place juste dessous ; reclic = fermer. */}
                  <tr
                    className="cursor-pointer"
                    onClick={() => setExpandedType((v) => (v === type.slug ? null : type.slug))}
                    data-testid={`type-row-${type.slug}`}
                    aria-expanded={expandedType === type.slug}
                  >
                    <td
                      className="text-[16px] font-[600] [font-family:var(--font-heading)]"
                      style={{ paddingLeft: `calc(var(--space-2) + ${depth} * var(--space-4))` }}
                    >
                      <span className="mr-1.5 inline-flex align-middle text-ink/[0.4]">
                        {expandedType === type.slug
                          ? <CaretDown size={13} weight="duotone" />
                          : <CaretRight size={13} weight="duotone" />}
                      </span>
                      {type.label}
                    </td>
                    <td className="text-accent-700 [font-family:var(--font-mono)] text-[13px]">
                      {type.slug}
                    </td>
                    <td>
                      {type.parent_slug === null ? (
                        <span className="tag tag-accent">{t('types.baseType')}</span>
                      ) : (
                        <span className="text-ink/[0.6]">{type.parent_slug}</span>
                      )}
                    </td>
                    <td className="max-w-[260px] truncate text-[13px] text-ink/[0.6]"
                      data-testid={`props-summary-${type.slug}`}>
                      {(type.properties ?? []).length > 0
                        ? (type.properties ?? []).map((p) => p.label).join(' · ')
                        : t('types.noProps')}
                    </td>
                    <td className="whitespace-nowrap text-ink/[0.55]"
                      data-testid={`docs-count-${type.slug}`}>
                      {t('types.docsCount', { count: type.documents_count ?? 0 })}
                    </td>
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="icon"
                        size="sm"
                        className="text-accent-2-700"
                        title={t('types.delete')}
                        aria-label={`${t('types.delete')} ${type.label}`}
                        onClick={() => { setDeleteTarget(type.slug); setDeleteError(null) }}
                        data-testid={`delete-${type.slug}`}
                      >
                        <Trash size={14} weight="duotone" />
                      </Button>
                    </td>
                  </tr>
                  {expandedType === type.slug && (
                    <tr>
                      <td colSpan={6} className="border-b-0 p-0">
                        <TypePropertiesPanel
                          ws={ws!}
                          type={type}
                          onClose={() => setExpandedType(null)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
      )}

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
                  {tpl.label} (v{tpl.version}) — {tpl.template}
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

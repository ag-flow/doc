import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowClockwise, DownloadSimple, Plus, PencilSimple, Trash, X } from '@phosphor-icons/react'
import { api, galleryApi, templatesApi } from '../lib/api'
import type { GalleryPullDiff, GallerySourceOut, RemoteTemplateInfo, TemplateInfo } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { SectionHead } from '../components/SectionHead'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, ErrorLine, TableSkeleton } from '../components/ui/states'
import { YamlEditor, type YamlEditorHandle } from '../components/YamlEditor'

/** Titre de section interne : surtitre + filet fin (pas de carte). */
function SubSection({ title, children, actions }: {
  title: string
  actions?: React.ReactNode
  children?: React.ReactNode
}) {
  return (
    <section className="mt-12 first:mt-0">
      <div className="flex items-end gap-4">
        <h3 className="m-0">{title}</h3>
        <span className="flex-1" />
        {actions}
      </div>
      <div className="mt-2 mb-5 h-px bg-[var(--color-divider)]" />
      {children}
    </section>
  )
}

// ── Installés ────────────────────────────────────────────────────────────────

function InstalledSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const editorRef = useRef<YamlEditorHandle>(null)

  const editRequestRef = useRef(0)
  const [editTarget, setEditTarget] = useState<TemplateInfo | null>(null)
  const [yamlContent, setYamlContent] = useState<string | null>(null)
  const [yamlLoadError, setYamlLoadError] = useState<string | null>(null)
  const [editSaving, setEditSaving] = useState(false)
  const [editSaveError, setEditSaveError] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<TemplateInfo | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const uploadInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery<TemplateInfo[]>({
    queryKey: ['templates'],
    queryFn: () => api.get<TemplateInfo[]>('/templates'),
  })

  async function openEdit(tpl: TemplateInfo) {
    const requestId = ++editRequestRef.current
    setEditTarget(tpl)
    setYamlContent(null)
    setYamlLoadError(null)
    setEditSaveError(null)
    try {
      const content = await templatesApi.getYaml(tpl.template)
      if (editRequestRef.current !== requestId) return // réponse hors-ordre : abandonnée
      setYamlContent(content)
    } catch (e) {
      if (editRequestRef.current !== requestId) return
      setYamlLoadError((e as Error).message)
    }
  }

  /** Télécharge l'export aplati (JSON) du template — appel authentifié puis
   *  déclenchement du download côté navigateur. */
  async function exportTemplate(slug: string) {
    const blob = await templatesApi.exportBlob(slug)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${slug}.json`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  /** Lit le fichier YAML choisi et l'installe comme nouveau template global. */
  async function importFile(file: File) {
    setImporting(true)
    setImportError(null)
    try {
      const content = await file.text()
      await templatesApi.create(content)
      void qc.invalidateQueries({ queryKey: ['templates'] })
    } catch (e) {
      // 409 : slug déjà installé — 422 : YAML / héritage invalide.
      setImportError((e as Error).message)
    } finally {
      setImporting(false)
    }
  }

  function closeEdit() {
    editRequestRef.current++ // invalide toute requête d'édition en vol
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
      // 409 : template utilisé — le détail liste les blocs concernés.
      setDeleteError((e as Error).message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <SubSection
      title={t('tpl.installedTitle')}
      actions={
        <>
          <input
            ref={uploadInputRef}
            type="file"
            accept=".yaml,.yml,text/yaml,application/x-yaml"
            className="hidden"
            data-testid="tpl-import-input"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void importFile(file)
              e.target.value = '' // ré-import du même fichier possible
            }}
          />
          <Button
            size="sm"
            variant="secondary"
            disabled={importing}
            onClick={() => uploadInputRef.current?.click()}
            data-testid="tpl-import-btn"
          >
            <Plus size={13} weight="duotone" />
            {importing ? t('tpl.importingFile') : t('tpl.importFile')}
          </Button>
        </>
      }
    >
      {importError && <ErrorLine message={importError} testId="tpl-import-error" />}
      {isLoading ? (
        <TableSkeleton rows={3} columns={4} testId="loading" />
      ) : isError ? (
        <ErrorLine message={t('error.generic')} testId="error" />
      ) : !data?.length ? (
        <EmptyState testId="empty" message={`${t('tpl.emptyTitle')} ${t('tpl.emptyHint')}`} />
      ) : (
        <table className="table" data-testid="template-list">
          <thead>
            <tr>
              <th>{t('tpl.colTemplate')}</th>
              <th>{t('tpl.colVersion')}</th>
              <th>{t('tpl.colTypes')}</th>
              <th>{t('tpl.colBlocks')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.map((tpl) => (
              <tr key={tpl.template} data-testid={`tpl-card-${tpl.template}`}>
                <td>
                  <span className="text-[16px] font-[600] [font-family:var(--font-heading)]">
                    {tpl.label}
                  </span>
                  <span className="ml-2 text-[12px] text-accent-700 [font-family:var(--font-mono)]">
                    {tpl.template}
                  </span>
                </td>
                <td className="[font-family:var(--font-mono)] text-[13px]">v{tpl.version}</td>
                <td className="max-w-[300px]">
                  <span className="flex flex-wrap gap-1.5">
                    {tpl.type_slugs.map((slug) => (
                      <span key={slug} className="tag tag-neutral text-[10px]">{slug}</span>
                    ))}
                  </span>
                </td>
                <td className="whitespace-nowrap text-ink/[0.55]" data-testid={`tpl-blocks-${tpl.template}`}>
                  {t('tpl.blocksCount', { count: tpl.blocks_count ?? 0 })}
                </td>
                <td className="whitespace-nowrap text-right">
                  <Button variant="icon" size="sm" title={t('tpl.export')}
                    aria-label={`${t('tpl.export')} ${tpl.template}`}
                    onClick={() => void exportTemplate(tpl.template)}
                    data-testid={`export-btn-${tpl.template}`}>
                    <DownloadSimple size={14} weight="duotone" />
                  </Button>
                  <Button variant="icon" size="sm" title={t('common.edit')}
                    aria-label={`${t('common.edit')} ${tpl.template}`}
                    onClick={() => void openEdit(tpl)} data-testid={`edit-btn-${tpl.template}`}>
                    <PencilSimple size={14} weight="duotone" />
                  </Button>
                  <Button variant="icon" size="sm" title={t('common.delete')}
                    aria-label={`${t('common.delete')} ${tpl.template}`}
                    className="text-accent-2-700"
                    onClick={() => { setDeleteTarget(tpl); setDeleteError(null) }}
                    data-testid={`delete-btn-${tpl.template}`}>
                    <Trash size={14} weight="duotone" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* ── Modale édition YAML ── */}
      {editTarget && (
        <div className="dialog-backdrop z-50" data-testid="edit-modal">
          <div className="dialog w-full !max-w-4xl" style={{ maxHeight: '90vh' }}
            role="dialog" aria-modal="true">
            <div className="flex items-center justify-between">
              <h4 className="dialog-title m-0">
                {t('tpl.editTitle', { template: editTarget.template })}
              </h4>
              <button type="button" onClick={closeEdit} aria-label={t('common.close', 'Fermer')}
                className="border-0 bg-transparent p-1 text-ink/[0.4] hover:text-ink">
                <X size={16} weight="bold" />
              </button>
            </div>
            <div className="min-h-0 flex-1">
              {yamlLoadError && <p className="field-error m-0 mb-2">{yamlLoadError}</p>}
              {yamlContent === null && !yamlLoadError && (
                <p className="text-muted text-[13px]">{t('common.loading')}</p>
              )}
              {yamlContent !== null && (
                <div className="overflow-hidden rounded-md border border-[var(--color-divider)]"
                  style={{ height: '60vh' }}>
                  <YamlEditor ref={editorRef} initialValue={yamlContent} />
                </div>
              )}
            </div>
            <div aria-live="polite" className="empty:hidden">
              {editSaveError && (
                <p className="field-error m-0" data-testid="edit-error">{editSaveError}</p>
              )}
            </div>
            <div className="dialog-actions m-0 border-t border-[var(--color-divider)] pt-3">
              <Button variant="secondary" onClick={closeEdit} disabled={editSaving}>
                {t('common.cancel')}
              </Button>
              <Button onClick={() => void saveEdit()} disabled={editSaving || yamlContent === null}
                data-testid="edit-save-btn">
                {editSaving ? t('common.loading') : t('common.save')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <ConfirmDialog
          testId="delete-modal"
          title={t('tpl.deleteTitle')}
          message={t('tpl.deleteConfirm', { template: deleteTarget.template })}
          impactMessage={
            deleteTarget.blocks_count > 0
              ? t('tpl.blocksCount', { count: deleteTarget.blocks_count })
              : undefined
          }
          confirmLabel={t('common.delete')}
          confirmTestId="delete-confirm-btn"
          pending={deleting}
          error={deleteError}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </SubSection>
  )
}

// ── Galerie ──────────────────────────────────────────────────────────────────

function GalleryTemplates({ sourceUrl, onInstalled }: {
  sourceUrl: string
  onInstalled: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const [items, setItems] = useState<RemoteTemplateInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [pulling, setPulling] = useState<string | null>(null)
  const [pullMsg, setPullMsg] = useState<{ msg: string; ok: boolean } | null>(null)
  // Mise à jour : le diff (types/propriétés ajoutés) s'affiche AVANT confirmation.
  const [updateDiff, setUpdateDiff] = useState<GalleryPullDiff | null>(null)

  async function load() {
    setLoading(true)
    setLoadError(null)
    setPullMsg(null)
    try {
      const data = await galleryApi.list(sourceUrl)
      setItems(data)
    } catch (e) {
      setLoadError((e as Error).message)
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [sourceUrl]) // eslint-disable-line react-hooks/exhaustive-deps

  async function doPull(templateSlug: string) {
    setPulling(templateSlug)
    setPullMsg(null)
    try {
      const result = await galleryApi.pull(sourceUrl, templateSlug)
      setPullMsg({
        msg: t('tpl.gallery.pullSuccess', { template: result.template, version: result.version }),
        ok: true,
      })
      void qc.invalidateQueries({ queryKey: ['templates'] })
      setItems((prev) =>
        prev.map((item) =>
          item.template === templateSlug
            ? { ...item, installed: true, update_available: false }
            : item,
        ),
      )
      onInstalled()
    } catch (e) {
      setPullMsg({ msg: (e as Error).message, ok: false })
    } finally {
      setPulling(null)
    }
  }

  /** Installer = direct ; mettre à jour = diff d'abord, confirmation ensuite. */
  async function pullTemplate(tpl: RemoteTemplateInfo) {
    if (!tpl.update_available) {
      await doPull(tpl.template)
      return
    }
    setPulling(tpl.template)
    setPullMsg(null)
    try {
      setUpdateDiff(await galleryApi.pullDiff(sourceUrl, tpl.template))
    } catch (e) {
      setPullMsg({ msg: (e as Error).message, ok: false })
    } finally {
      setPulling(null)
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <span className="max-w-md truncate text-[12px] text-ink/[0.45] [font-family:var(--font-mono)]">
          {sourceUrl}
        </span>
        <Button size="sm" variant="secondary" onClick={() => void load()} disabled={loading}
          data-testid="gallery-refresh-btn">
          <ArrowClockwise size={13} weight="duotone" />
          {loading ? t('tpl.gallery.loading') : t('tpl.gallery.refresh')}
        </Button>
      </div>

      <ErrorLine message={loadError} testId="gallery-load-error" />
      <div aria-live="polite" className="empty:hidden">
        {pullMsg && (
          <p className={`mb-4 text-[13px] ${pullMsg.ok ? 'text-accent-700' : 'text-accent-2-700'}`}>
            {pullMsg.msg}
          </p>
        )}
      </div>

      {!loading && items.length === 0 && !loadError && (
        <p className="text-muted text-[13px]">{t('tpl.gallery.empty')}</p>
      )}

      <ul className="m-0 list-none p-0">
        {items.map((tpl) => {
          const isPulling = pulling === tpl.template
          return (
            <li key={tpl.template}
              className="flex items-center gap-3 border-b border-[var(--color-divider)] py-3"
              data-testid={`gallery-card-${tpl.template}`}>
              <div className="min-w-0 flex-1">
                <span className="text-[15px] font-[600] [font-family:var(--font-heading)]">
                  {tpl.label}
                </span>
                <span className="ml-2 text-[12px] text-accent-700 [font-family:var(--font-mono)]">
                  {tpl.template} · v{tpl.version}
                </span>
                <span className="mt-1 flex flex-wrap gap-1.5">
                  {tpl.type_slugs.map((slug) => (
                    <span key={slug} className="tag tag-neutral text-[10px]">{slug}</span>
                  ))}
                </span>
              </div>
              <div className="shrink-0">
                {tpl.installed && !tpl.update_available ? (
                  <span className="text-[12px] font-[600] text-accent-700">
                    ✓ {t('tpl.gallery.upToDate')}
                  </span>
                ) : (
                  <Button size="sm" variant={tpl.update_available ? 'secondary' : 'primary'}
                    onClick={() => void pullTemplate(tpl)}
                    disabled={isPulling || pulling !== null}
                    data-testid={`gallery-install-${tpl.template}`}>
                    {isPulling
                      ? t('tpl.gallery.pulling')
                      : tpl.update_available
                        ? t('tpl.gallery.update')
                        : t('tpl.gallery.install')}
                  </Button>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      {updateDiff && (
        <ConfirmDialog
          testId="update-diff-dialog"
          title={t('tpl.updateTitle', { template: updateDiff.template })}
          destructive={false}
          message={
            <>
              <p className="m-0">
                {t('tpl.updateVersion', {
                  from: updateDiff.installed_version ?? '—',
                  to: updateDiff.remote_version,
                })}
              </p>
              {updateDiff.new_types.length > 0 && (
                <p className="m-0 mt-2">
                  {t('tpl.updateNewTypes')}{' '}
                  <span className="[font-family:var(--font-mono)] text-[12px]">
                    {updateDiff.new_types.join(', ')}
                  </span>
                </p>
              )}
              {updateDiff.new_properties.length > 0 && (
                <p className="m-0 mt-2">
                  {t('tpl.updateNewProps')}{' '}
                  <span className="[font-family:var(--font-mono)] text-[12px]">
                    {updateDiff.new_properties.join(', ')}
                  </span>
                </p>
              )}
              {updateDiff.new_types.length === 0 && updateDiff.new_properties.length === 0 && (
                <p className="m-0 mt-2 text-ink/[0.6]">{t('tpl.updateNoChange')}</p>
              )}
            </>
          }
          confirmLabel={t('tpl.updateConfirm')}
          onConfirm={() => {
            const slug = updateDiff.template
            setUpdateDiff(null)
            void doPull(slug)
          }}
          onCancel={() => setUpdateDiff(null)}
        />
      )}
    </div>
  )
}

/** Normalise une URL de source : strip toc.txt / slash final, et convertit les
 *  pages GitHub (github.com/…/blob|tree/…) vers leur équivalent raw — la galerie
 *  a besoin du contenu brut, pas de la page HTML. */
export function normalizeSourceUrl(url: string): string {
  const cleaned = url.trim().replace(/\/toc\.txt$/, '').replace(/\/$/, '')
  const gh = cleaned.match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/(?:blob|tree)\/([^/]+)\/(.+)$/)
  if (gh) {
    return `https://raw.githubusercontent.com/${gh[1]}/${gh[2]}/refs/heads/${gh[3]}/${gh[4]}`
  }
  return cleaned
}

function GallerySection() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const [activeSource, setActiveSource] = useState<GallerySourceOut | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newLabel, setNewLabel] = useState('')
  const [newUrl, setNewUrl] = useState('')
  const [addError, setAddError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const { data: sources = [], refetch: refetchSources } = useQuery<GallerySourceOut[]>({
    queryKey: ['gallery-sources'],
    queryFn: () => galleryApi.listSources(),
  })

  // Première source sélectionnée d'office : la galerie s'affiche sans clic.
  useEffect(() => {
    if (activeSource === null && sources.length > 0) setActiveSource(sources[0])
  }, [sources, activeSource])

  async function addSource() {
    if (!newLabel.trim() || !newUrl.trim()) return
    const trimmedUrl = normalizeSourceUrl(newUrl)
    if (sources.some((s) => s.url === trimmedUrl)) {
      setAddError('Cette source est déjà dans la liste')
      return
    }
    if (/\.(yaml|yml|txt)$/i.test(trimmedUrl)) {
      setAddError("L'URL doit pointer vers un répertoire de base, pas un fichier")
      return
    }
    if (/^https:\/\/github\.com\//.test(trimmedUrl)) {
      setAddError(t('tpl.gallery.sourceUrlGithubError'))
      return
    }
    setAdding(true)
    setAddError(null)
    try {
      const created = await galleryApi.addSource(newLabel.trim(), trimmedUrl)
      await refetchSources()
      setActiveSource(created)
      setShowAddForm(false)
      setNewLabel('')
      setNewUrl('')
    } catch (e) {
      setAddError((e as Error).message)
    } finally {
      setAdding(false)
    }
  }

  async function deleteSource(src: GallerySourceOut) {
    if (!src.id) return
    setDeletingId(src.id)
    try {
      await galleryApi.deleteSource(src.id)
      if (activeSource?.id === src.id) setActiveSource(null)
      await refetchSources()
      void qc.invalidateQueries({ queryKey: ['gallery-sources'] })
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <SubSection
      title={t('tpl.galleryTitle')}
      actions={
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => { setShowAddForm((v) => !v); setAddError(null) }}
          data-testid="gallery-add-source-btn"
        >
          {showAddForm ? t('common.cancel') : <><Plus size={12} weight="duotone" /> {t('tpl.gallery.addSource')}</>}
        </button>
      }
    >
      {/* Sources rappelées sous le titre de section. */}
      <div className="mb-5 flex flex-wrap items-center gap-2" data-testid="gallery-sources">
        {sources.length === 0 && !showAddForm && (
          <p className="text-muted m-0 text-[13px]">{t('tpl.gallery.noSources')}</p>
        )}
        {sources.map((src) => (
          <span key={src.id ?? 'builtin'}
            className={`tag gap-1.5 ${activeSource?.url === src.url ? 'tag-accent' : 'tag-outline'}`}
            data-testid={`gallery-source-${src.id ?? 'builtin'}`}>
            <button type="button" title={src.url}
              className="border-0 bg-transparent p-0 text-inherit"
              onClick={() => setActiveSource(src)}>
              {src.label}
            </button>
            {src.builtin && <span className="opacity-60">{t('tpl.gallery.builtin')}</span>}
            {!src.builtin && src.id && (
              <button type="button"
                className="border-0 bg-transparent p-0 text-inherit opacity-70 hover:opacity-100"
                onClick={() => void deleteSource(src)}
                disabled={deletingId === src.id}
                data-testid={`gallery-delete-source-${src.id}`}
                aria-label={`${t('tpl.gallery.deleteSourceConfirm')} ${src.label}`}
                title={t('tpl.gallery.deleteSourceConfirm')}>
                <X size={11} weight="bold" />
              </button>
            )}
          </span>
        ))}
      </div>

      {showAddForm && (
        <div className="mb-5 flex max-w-xl flex-col gap-2">
          <Input
            placeholder={t('tpl.gallery.sourceLabelPlaceholder')}
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            data-testid="gallery-new-label"
          />
          <Input
            placeholder={t('tpl.gallery.sourceUrlPlaceholder')}
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void addSource() }}
            data-testid="gallery-new-url"
          />
          <p className="text-muted m-0 text-[12px]" data-testid="gallery-url-hint">
            {t('tpl.gallery.sourceUrlHint')}
          </p>
          {addError && <p className="field-error m-0">{addError}</p>}
          <Button size="sm" onClick={() => void addSource()}
            disabled={adding || !newLabel.trim() || !newUrl.trim()}
            data-testid="gallery-add-confirm">
            {adding ? t('common.loading') : t('tpl.gallery.add')}
          </Button>
        </div>
      )}

      {activeSource ? (
        <GalleryTemplates
          key={activeSource.url}
          sourceUrl={activeSource.url}
          onInstalled={() => void refetchSources()}
        />
      ) : (
        <p className="text-muted text-[13px]">{t('tpl.gallery.selectSource')}</p>
      )}
    </SubSection>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function TemplateList() {
  const { t } = useTranslation()
  return (
    <div className="mx-auto max-w-[1000px] px-6 pt-11 pb-24">
      <SectionHead kicker={t('tpl.kicker')} title={t('tpl.title')} />
      <InstalledSection />
      <GallerySection />
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, galleryApi, templatesApi } from '../lib/api'
import type { GallerySourceOut, RemoteTemplateInfo, TemplateInfo } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { YamlEditor, type YamlEditorHandle } from '../components/YamlEditor'

// ── Onglet Bibliothèque locale ───────────────────────────────────────────────

function LocalLibrary() {
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
      <div className="py-12 text-center text-gray-400" data-testid="empty">
        <p className="text-lg font-medium mb-2">{t('tpl.emptyTitle')}</p>
        <p className="text-sm">{t('tpl.emptyHint')}</p>
      </div>
    )
  }

  return (
    <>
      <div className="grid gap-4" data-testid="template-list">
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
    </>
  )
}

// ── Onglet Galerie en ligne ──────────────────────────────────────────────────

function GalleryTemplates({
  sourceUrl,
  onInstalled,
}: {
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

  async function pullTemplate(tpl: RemoteTemplateInfo) {
    setPulling(tpl.template)
    setPullMsg(null)
    try {
      const result = await galleryApi.pull(sourceUrl, tpl.template)
      setPullMsg({
        msg: t('tpl.gallery.pullSuccess', { template: result.template, version: result.version }),
        ok: true,
      })
      void qc.invalidateQueries({ queryKey: ['templates'] })
      setItems(prev =>
        prev.map(item =>
          item.template === tpl.template
            ? { ...item, installed: true, update_available: false }
            : item
        )
      )
      onInstalled()
    } catch (e) {
      setPullMsg({ msg: (e as Error).message, ok: false })
    } finally {
      setPulling(null)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs text-gray-400 font-mono truncate max-w-xs">{sourceUrl}</span>
        <Button size="sm" variant="secondary" onClick={() => void load()} disabled={loading} data-testid="gallery-refresh-btn">
          {loading ? t('tpl.gallery.loading') : t('tpl.gallery.refresh')}
        </Button>
      </div>

      {loadError && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {loadError}
        </div>
      )}

      {pullMsg && (
        <div className={`mb-4 rounded border px-4 py-2 text-sm ${pullMsg.ok ? 'border-green-200 bg-green-50 text-green-800' : 'border-red-200 bg-red-50 text-red-700'}`}>
          {pullMsg.msg}
        </div>
      )}

      {!loading && items.length === 0 && !loadError && (
        <p className="text-sm text-gray-400">{t('tpl.gallery.empty')}</p>
      )}

      <div className="grid gap-3">
        {items.map(tpl => {
          const isPulling = pulling === tpl.template
          const canInstall = !tpl.installed || tpl.update_available
          return (
            <div key={tpl.template} className="border rounded-lg p-4 bg-white shadow-sm" data-testid={`gallery-card-${tpl.template}`}>
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="font-mono text-sm font-semibold text-indigo-700">{tpl.template}</span>
                    <span className="font-mono text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded">v{tpl.version}</span>
                    <span className="text-gray-700 font-medium">{tpl.label}</span>
                    {tpl.installed && !tpl.update_available && (
                      <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded font-medium">✓ {t('tpl.gallery.upToDate')}</span>
                    )}
                    {tpl.update_available && (
                      <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-medium">↑ màj disponible</span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {tpl.type_slugs.map(slug => (
                      <span key={slug} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono">{slug}</span>
                    ))}
                  </div>
                </div>
                <div className="shrink-0">
                  {canInstall ? (
                    <Button size="sm" onClick={() => void pullTemplate(tpl)} disabled={isPulling || pulling !== null} data-testid={`gallery-install-${tpl.template}`}>
                      {isPulling ? t('tpl.gallery.pulling') : tpl.update_available ? t('tpl.gallery.update') : t('tpl.gallery.install')}
                    </Button>
                  ) : (
                    <span className="text-xs text-gray-400 font-medium px-2">{t('tpl.gallery.installed')}</span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function GalleryTab() {
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

  async function addSource() {
    if (!newLabel.trim() || !newUrl.trim()) return
    const trimmedUrl = newUrl.trim().replace(/\/toc\.txt$/, '').replace(/\/$/, '')
    if (sources.some(s => s.url === trimmedUrl)) {
      setAddError('Cette source est déjà dans la liste')
      return
    }
    if (/\.(yaml|yml|txt)$/i.test(trimmedUrl)) {
      setAddError("L'URL doit pointer vers un répertoire de base, pas un fichier")
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
    <div className="flex gap-6">
      {/* ── Panneau sources ── */}
      <div className="w-56 shrink-0">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{t('tpl.gallery.sources')}</span>
          <button
            className="text-indigo-600 hover:text-indigo-800 text-xs font-medium"
            onClick={() => { setShowAddForm(v => !v); setAddError(null) }}
            data-testid="gallery-add-source-btn"
          >
            {showAddForm ? '✕' : '+ ' + t('tpl.gallery.addSource')}
          </button>
        </div>

        {/* Formulaire ajout */}
        {showAddForm && (
          <div className="mb-3 rounded border border-indigo-100 bg-indigo-50 p-3 space-y-2">
            <Input
              placeholder={t('tpl.gallery.sourceLabelPlaceholder')}
              value={newLabel}
              onChange={e => setNewLabel(e.target.value)}
              className="text-sm h-8"
              data-testid="gallery-new-label"
            />
            <Input
              placeholder={t('tpl.gallery.sourceUrlPlaceholder')}
              value={newUrl}
              onChange={e => setNewUrl(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') void addSource() }}
              className="text-sm h-8"
              data-testid="gallery-new-url"
            />
            {addError && <p className="text-xs text-red-600">{addError}</p>}
            <Button size="sm" className="w-full" onClick={() => void addSource()} disabled={adding || !newLabel.trim() || !newUrl.trim()} data-testid="gallery-add-confirm">
              {adding ? t('common.loading') : t('tpl.gallery.add')}
            </Button>
          </div>
        )}

        {/* Liste des sources */}
        {sources.length === 0 && !showAddForm && (
          <p className="text-xs text-gray-400">{t('tpl.gallery.noSources')}</p>
        )}
        <ul className="space-y-1">
          {sources.map(src => (
            <li key={src.id ?? 'builtin'}>
              <div
                className={`group flex items-center gap-1 rounded px-2 py-1.5 cursor-pointer text-sm transition-colors ${
                  activeSource?.url === src.url
                    ? 'bg-indigo-100 text-indigo-800 font-medium'
                    : 'hover:bg-gray-100 text-gray-700'
                }`}
                onClick={() => setActiveSource(src)}
                data-testid={`gallery-source-${src.id ?? 'builtin'}`}
              >
                <span className="flex-1 truncate" title={src.url}>{src.label}</span>
                {src.builtin && (
                  <span className="text-xs text-gray-400 shrink-0">{t('tpl.gallery.builtin')}</span>
                )}
                {!src.builtin && src.id && (
                  <button
                    className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-opacity shrink-0"
                    onClick={e => { e.stopPropagation(); void deleteSource(src) }}
                    disabled={deletingId === src.id}
                    data-testid={`gallery-delete-source-${src.id}`}
                    title={t('tpl.gallery.deleteSourceConfirm')}
                  >
                    ✕
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* ── Panneau templates ── */}
      <div className="flex-1 min-w-0">
        {activeSource ? (
          <GalleryTemplates
            key={activeSource.url}
            sourceUrl={activeSource.url}
            onInstalled={() => void refetchSources()}
          />
        ) : (
          <p className="text-sm text-gray-400 mt-2">{t('tpl.gallery.selectSource')}</p>
        )}
      </div>
    </div>
  )
}

// ── Page principale avec onglets ─────────────────────────────────────────────

type Tab = 'local' | 'gallery'

export default function TemplateList() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<Tab>('local')

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">{t('tpl.title')}</h1>

      {/* Onglets */}
      <div className="flex gap-0 border-b border-gray-200 mb-6">
        {(['local', 'gallery'] as const).map(tab => (
          <button
            key={tab}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => setActiveTab(tab)}
            data-testid={`tab-${tab}`}
          >
            {tab === 'local' ? t('tpl.tabLocal') : t('tpl.tabGallery')}
          </button>
        ))}
      </div>

      {activeTab === 'local' ? <LocalLibrary /> : <GalleryTab />}
    </div>
  )
}

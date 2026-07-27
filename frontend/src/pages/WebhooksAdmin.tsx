import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { PencilSimple, Plus, Trash, X } from '@phosphor-icons/react'
import { webhooksApi, ALL_EVENTS, type WebhookOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { SectionHead } from '../components/SectionHead'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, ErrorLine, TableSkeleton } from '../components/ui/states'
import { HmacSecretsTab } from '../components/HmacSecretsTab'

type FormState = {
  label: string
  url: string
  headers: { key: string; value: string }[]
  events: string[]
  active: boolean
}

const EMPTY_FORM: FormState = {
  label: '',
  url: '',
  headers: [],
  events: [],
  active: true,
}

function headersToDict(rows: { key: string; value: string }[]): Record<string, string> {
  return Object.fromEntries(rows.filter((r) => r.key.trim()).map((r) => [r.key, r.value]))
}

function dictToHeaders(d: Record<string, string>): { key: string; value: string }[] {
  return Object.entries(d).map(([key, value]) => ({ key, value }))
}

function whToForm(wh: WebhookOut): FormState {
  return {
    label: wh.label,
    url: wh.url,
    headers: dictToHeaders(wh.headers),
    events: [...wh.events],
    active: wh.active,
  }
}

function WebhooksTab() {
  const { wsSlug: ws } = useParams<{ wsSlug: string }>()
  const { t } = useTranslation()
  const qc = useQueryClient()

  const [editId, setEditId] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [testResult, setTestResult] = useState<
    { id: string; status: number | null; error: string | null; durationMs: number } | null
  >(null)
  const [apiError, setApiError] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<WebhookOut | null>(null)

  const { data: webhooks = [], isLoading } = useQuery<WebhookOut[]>({
    queryKey: ['webhooks', ws],
    queryFn: () => webhooksApi.list(ws!),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['webhooks', ws] })

  const createMut = useMutation({
    mutationFn: () =>
      webhooksApi.create(ws!, {
        label: form.label,
        url: form.url,
        headers: headersToDict(form.headers),
        events: form.events,
        active: form.active,
      }),
    onSuccess: () => { invalidate(); resetForm() },
    onError: (e: Error) => setApiError(e.message),
  })

  const updateMut = useMutation({
    mutationFn: () =>
      webhooksApi.update(ws!, editId!, {
        label: form.label,
        url: form.url,
        headers: headersToDict(form.headers),
        events: form.events,
        active: form.active,
      }),
    onSuccess: () => { invalidate(); resetForm() },
    onError: (e: Error) => setApiError(e.message),
  })

  // Activer / suspendre sans ouvrir le formulaire.
  const toggleMut = useMutation({
    mutationFn: (wh: WebhookOut) => webhooksApi.update(ws!, wh.id, { active: !wh.active }),
    onSuccess: invalidate,
    onError: (e: Error) => setApiError(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => webhooksApi.delete(ws!, id),
    onSuccess: () => { setDeleteTarget(null); void invalidate() },
    onError: (e: Error) => setApiError(e.message),
  })

  const testMut = useMutation({
    mutationFn: (id: string) => webhooksApi.test(ws!, id),
    // DoD : le résultat s'affiche EN LIGNE (code + temps de réponse), pas en toast.
    onSuccess: (data, id) =>
      setTestResult({ id, status: data.status_code, error: data.error, durationMs: data.duration_ms }),
    onError: (e: Error) => { setTestResult(null); setApiError(e.message) },
  })

  function resetForm() {
    setShowForm(false)
    setEditId(null)
    setForm(EMPTY_FORM)
    setApiError('')
  }

  function openCreate() {
    setEditId(null)
    setForm(EMPTY_FORM)
    setShowForm(true)
    setApiError('')
  }

  function openEdit(wh: WebhookOut) {
    setEditId(wh.id)
    setForm(whToForm(wh))
    setShowForm(true)
    setApiError('')
  }

  function toggleEvent(ev: string) {
    setForm((f) => ({
      ...f,
      events: f.events.includes(ev) ? f.events.filter((e) => e !== ev) : [...f.events, ev],
    }))
  }

  function setHeaderField(i: number, field: 'key' | 'value', val: string) {
    setForm((f) => ({
      ...f,
      headers: f.headers.map((r, idx) => (idx === i ? { ...r, [field]: val } : r)),
    }))
  }

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setApiError('')
    if (editId) updateMut.mutate()
    else createMut.mutate()
  }

  if (isLoading) return <TableSkeleton rows={3} columns={4} />

  return (
    <>
      <div className="mb-6 flex items-start gap-4">
        <p className="m-0 max-w-[64ch] flex-1 text-[16px] leading-[1.6] text-ink/[0.68]">
          Un webhook sortant poste une requête HTTP vers une URL externe à chaque événement du
          workspace (création, modification, suppression) — payload signé HMAC-SHA256. Utilisez-les
          pour notifier un outil tiers ou déclencher un traitement sans polling.
        </p>
        <Button onClick={openCreate} className="shrink-0" data-testid="create-webhook-btn">
          <Plus size={15} weight="duotone" /> {t('webhooks.create')}
        </Button>
      </div>

      <ErrorLine message={apiError} testId="wh-api-error" />

      {showForm && (
        <form
          className="card elev-sm mb-8 max-w-[640px]"
          onSubmit={submit}
          data-testid="webhook-form"
        >
          <h5 className="m-0">{editId ? t('webhooks.edit') : t('webhooks.create')}</h5>

          <Field label={t('webhooks.label')} htmlFor="wh-label">
            <Input
              id="wh-label"
              data-testid="wh-label"
              value={form.label}
              onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              required
            />
          </Field>

          <Field label={t('webhooks.url')} htmlFor="wh-url" hint={t('webhooks.urlHint')}>
            <Input
              id="wh-url"
              data-testid="wh-url"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              placeholder="https://example.com/{id_document}"
              required
            />
          </Field>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[12px] text-ink/[0.7]">{t('webhooks.headers')}</span>
              <Button type="button" variant="ghost" size="sm"
                onClick={() => setForm((f) => ({ ...f, headers: [...f.headers, { key: '', value: '' }] }))}
                data-testid="add-header-btn">
                <Plus size={12} weight="duotone" /> {t('common.add', 'Ajouter')}
              </Button>
            </div>
            {form.headers.map((row, i) => (
              <div key={i} className="mb-1.5 flex items-center gap-2" data-testid={`header-row-${i}`}>
                <Input
                  placeholder={t('webhooks.headerKey')}
                  value={row.key}
                  onChange={(e) => setHeaderField(i, 'key', e.target.value)}
                  className="w-44"
                  data-testid={`header-key-${i}`}
                />
                <Input
                  placeholder={t('webhooks.headerValue')}
                  value={row.value}
                  onChange={(e) => setHeaderField(i, 'value', e.target.value)}
                  data-testid={`header-value-${i}`}
                />
                <button type="button"
                  onClick={() => setForm((f) => ({ ...f, headers: f.headers.filter((_, idx) => idx !== i) }))}
                  className="border-0 bg-transparent p-1 text-ink/[0.4] hover:text-accent-2-700"
                  aria-label={`${t('common.delete')} header ${row.key || i + 1}`}
                  data-testid={`remove-header-${i}`}>
                  <X size={14} weight="bold" />
                </button>
              </div>
            ))}
          </div>

          <div>
            <span className="mb-1 block text-[12px] text-ink/[0.7]">{t('webhooks.events')}</span>
            <div className="flex gap-4">
              {ALL_EVENTS.map((ev) => (
                <label key={ev} className="flex cursor-pointer items-center gap-1.5 text-[14px]">
                  <input
                    type="checkbox"
                    checked={form.events.includes(ev)}
                    onChange={() => toggleEvent(ev)}
                    data-testid={`event-${ev}`}
                  />
                  <span>{ev.replace('document.', '')}</span>
                </label>
              ))}
            </div>
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-[14px]">
            <input
              type="checkbox"
              checked={form.active}
              onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))}
              data-testid="wh-active"
            />
            {t('webhooks.active')}
          </label>

          <div className="flex gap-2">
            <Button type="submit" disabled={createMut.isPending || updateMut.isPending}
              data-testid="wh-submit">
              {t('common.save')}
            </Button>
            <Button type="button" variant="secondary" onClick={resetForm}>
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      )}

      {webhooks.length === 0 && !showForm ? (
        <EmptyState
          testId="wh-empty"
          message={t('webhooks.empty')}
          action={
            <Button onClick={openCreate}>
              <Plus size={15} weight="duotone" /> {t('webhooks.create')}
            </Button>
          }
        />
      ) : webhooks.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>{t('webhooks.colTarget', 'Cible')}</th>
              <th>{t('webhooks.events')}</th>
              <th>{t('webhooks.colState', 'État')}</th>
              <th>{t('webhooks.colTest', 'Dernier test')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {webhooks.map((wh) => (
              <tr key={wh.id} data-testid={`webhook-row-${wh.id}`}>
                <td className="max-w-[280px]">
                  <span className="block truncate text-[15px] font-[600] [font-family:var(--font-heading)]">
                    {wh.label}
                  </span>
                  <span className="block truncate text-[12px] text-ink/[0.5] [font-family:var(--font-mono)]">
                    {wh.url}
                  </span>
                </td>
                <td className="text-[12px] text-ink/[0.6]">
                  {wh.events.map((e) => e.replace('document.', '')).join(', ') || '—'}
                </td>
                <td>
                  {/* Activer / suspendre sans quitter la liste. */}
                  <button
                    type="button"
                    onClick={() => toggleMut.mutate(wh)}
                    disabled={toggleMut.isPending}
                    className="border-0 bg-transparent p-0"
                    title={wh.active ? t('webhooks.suspend', 'Suspendre') : t('webhooks.activate', 'Activer')}
                    data-testid={`wh-status-${wh.id}`}
                  >
                    <span className={`tag ${wh.active ? 'tag-accent' : 'tag-neutral'}`}>
                      {wh.active ? t('webhooks.statusActive') : t('webhooks.statusInactive')}
                    </span>
                  </button>
                </td>
                <td className="text-[13px]" data-testid={`test-cell-${wh.id}`}>
                  {/* DoD : code retour + temps de réponse, en ligne. */}
                  {testResult?.id === wh.id ? (
                    testResult.error ? (
                      <span className="text-accent-2-700" data-testid={`test-result-${wh.id}`}>
                        {t('webhooks.testError')} : {testResult.error}
                      </span>
                    ) : (
                      <span
                        className={(testResult.status ?? 500) < 400 ? 'text-accent-700' : 'text-accent-2-700'}
                        data-testid={`test-result-${wh.id}`}
                      >
                        HTTP {testResult.status} · {testResult.durationMs} ms
                      </span>
                    )
                  ) : (
                    <span className="text-ink/[0.4]">—</span>
                  )}
                </td>
                <td className="whitespace-nowrap text-right">
                  <Button variant="ghost" size="sm"
                    onClick={() => testMut.mutate(wh.id)}
                    disabled={testMut.isPending}
                    data-testid={`test-webhook-${wh.id}`}>
                    {t('webhooks.test')}
                  </Button>
                  <Button variant="icon" size="sm" title={t('common.edit')}
                    aria-label={`${t('common.edit')} ${wh.label}`}
                    onClick={() => openEdit(wh)} data-testid={`edit-webhook-${wh.id}`}>
                    <PencilSimple size={14} weight="duotone" />
                  </Button>
                  <Button variant="icon" size="sm" className="text-accent-2-700"
                    title={t('common.delete')}
                    aria-label={`${t('common.delete')} ${wh.label}`}
                    onClick={() => setDeleteTarget(wh)}
                    data-testid={`delete-webhook-${wh.id}`}>
                    <Trash size={14} weight="duotone" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {deleteTarget && (
        <ConfirmDialog
          testId="wh-delete-dialog"
          title={t('webhooks.deleteTitle', 'Supprimer le webhook')}
          message={`Supprimer « ${deleteTarget.label} » ? La cible ne recevra plus aucun événement.`}
          confirmLabel={t('webhooks.deleteConfirm', 'Supprimer le webhook')}
          pending={deleteMut.isPending}
          onConfirm={() => deleteMut.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </>
  )
}

// ── Page à deux onglets ───────────────────────────────────────────────────────

type Tab = 'webhooks' | 'hmac'

export function WebhooksAdmin() {
  const { wsSlug: ws } = useParams<{ wsSlug: string }>()
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('webhooks')

  const TabBtn = ({ id, children }: { id: Tab; children: React.ReactNode }) => (
    <button
      type="button"
      onClick={() => setTab(id)}
      className={`border-0 border-b-2 bg-transparent px-4 py-2 text-[14px] font-[600]
        [font-family:var(--font-heading)] [border-bottom-style:solid] transition-colors ${
          tab === id
            ? 'border-b-accent text-accent-700'
            : 'border-b-transparent text-ink/[0.55] hover:text-ink'
        }`}
      data-testid={`tab-${id}`}
    >
      {children}
    </button>
  )

  return (
    <div className="mx-auto max-w-[1000px] px-6 pt-11 pb-24" data-testid="webhooks-page">
      <SectionHead kicker={ws ?? ''} title={t('webhooks.title')} />

      <div className="mb-6 flex gap-1 border-b border-[var(--color-divider)]">
        <TabBtn id="webhooks">{t('webhooks.title')}</TabBtn>
        <TabBtn id="hmac">{t('webhooks.tabHmac', 'Secrets HMAC')}</TabBtn>
      </div>

      {tab === 'webhooks' && <WebhooksTab />}
      {tab === 'hmac' && <HmacSecretsTab />}
    </div>
  )
}

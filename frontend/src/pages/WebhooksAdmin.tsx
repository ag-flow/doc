import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { webhooksApi, ALL_EVENTS, type WebhookOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

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

export function WebhooksAdmin() {
  const { wsSlug: ws } = useParams<{ wsSlug: string }>()
  const { t } = useTranslation()
  const qc = useQueryClient()

  const [editId, setEditId] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [testResult, setTestResult] = useState<{ id: string; status: number | null; error: string | null } | null>(null)
  const [apiError, setApiError] = useState('')

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

  const deleteMut = useMutation({
    mutationFn: (id: string) => webhooksApi.delete(ws!, id),
    onSuccess: invalidate,
    onError: (e: Error) => setApiError(e.message),
  })

  const testMut = useMutation({
    mutationFn: (id: string) => webhooksApi.test(ws!, id),
    onSuccess: (data, id) => setTestResult({ id, status: data.status_code, error: data.error }),
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

  function addHeaderRow() {
    setForm((f) => ({ ...f, headers: [...f.headers, { key: '', value: '' }] }))
  }

  function removeHeaderRow(i: number) {
    setForm((f) => ({ ...f, headers: f.headers.filter((_, idx) => idx !== i) }))
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

  if (isLoading) return <p className="p-4">{t('common.loading')}</p>

  return (
    <div className="p-6 max-w-3xl mx-auto" data-testid="webhooks-page">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{t('webhooks.title')}</h1>
        <Button onClick={openCreate} data-testid="create-webhook-btn">
          {t('webhooks.create')}
        </Button>
      </div>

      {apiError && (
        <p className="text-red-600 mb-4 text-sm" data-testid="wh-api-error">
          {apiError}
        </p>
      )}

      {showForm && (
        <form
          className="mb-6 p-4 border rounded space-y-4"
          onSubmit={submit}
          data-testid="webhook-form"
        >
          <h2 className="font-semibold">
            {editId ? t('webhooks.edit') : t('webhooks.create')}
          </h2>

          <div>
            <label className="block text-sm font-medium mb-1">{t('webhooks.label')}</label>
            <Input
              data-testid="wh-label"
              value={form.label}
              onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">
              {t('webhooks.url')}{' '}
              <span className="font-mono text-xs text-gray-500">
                ({t('webhooks.urlHint')})
              </span>
            </label>
            <Input
              data-testid="wh-url"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              placeholder="https://example.com/{id_document}"
              required
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-sm font-medium">{t('webhooks.headers')}</label>
              <Button type="button" variant="secondary" onClick={addHeaderRow} data-testid="add-header-btn">
                +
              </Button>
            </div>
            {form.headers.map((row, i) => (
              <div key={i} className="flex gap-2 mb-1" data-testid={`header-row-${i}`}>
                <Input
                  placeholder={t('webhooks.headerKey')}
                  value={row.key}
                  onChange={(e) => setHeaderField(i, 'key', e.target.value)}
                  data-testid={`header-key-${i}`}
                />
                <Input
                  placeholder={t('webhooks.headerValue')}
                  value={row.value}
                  onChange={(e) => setHeaderField(i, 'value', e.target.value)}
                  data-testid={`header-value-${i}`}
                />
                <Button
                  type="button"
                  variant="danger"
                  onClick={() => removeHeaderRow(i)}
                  data-testid={`remove-header-${i}`}
                >
                  ×
                </Button>
              </div>
            ))}
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">{t('webhooks.events')}</label>
            <div className="flex gap-4">
              {ALL_EVENTS.map((ev) => (
                <label key={ev} className="flex items-center gap-1 text-sm cursor-pointer">
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

          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={form.active}
              onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))}
              data-testid="wh-active"
            />
            {t('webhooks.active')}
          </label>

          <div className="flex gap-2">
            <Button
              type="submit"
              disabled={createMut.isPending || updateMut.isPending}
              data-testid="wh-submit"
            >
              {t('common.save')}
            </Button>
            <Button type="button" variant="secondary" onClick={resetForm}>
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      )}

      {webhooks.length === 0 && !showForm && (
        <p className="text-gray-500 text-sm" data-testid="wh-empty">
          {t('webhooks.empty')}
        </p>
      )}

      <div className="space-y-3">
        {webhooks.map((wh) => (
          <div
            key={wh.id}
            className="border rounded p-4 flex items-start justify-between gap-4"
            data-testid={`webhook-row-${wh.id}`}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-medium">{wh.label}</span>
                <span
                  className={`text-xs px-1.5 py-0.5 rounded ${
                    wh.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                  }`}
                  data-testid={`wh-status-${wh.id}`}
                >
                  {wh.active ? t('webhooks.statusActive') : t('webhooks.statusInactive')}
                </span>
              </div>
              <p className="font-mono text-xs text-gray-500 truncate">{wh.url}</p>
              <p className="text-xs text-gray-400 mt-0.5">{wh.events.join(', ') || '—'}</p>
              {testResult?.id === wh.id && (
                <p
                  className={`text-xs mt-1 ${testResult.error ? 'text-red-600' : 'text-green-700'}`}
                  data-testid={`test-result-${wh.id}`}
                >
                  {testResult.error
                    ? `${t('webhooks.testError')} : ${testResult.error}`
                    : `HTTP ${testResult.status}`}
                </p>
              )}
            </div>
            <div className="flex gap-2 shrink-0">
              <Button
                variant="secondary"
                onClick={() => testMut.mutate(wh.id)}
                disabled={testMut.isPending}
                data-testid={`test-webhook-${wh.id}`}
              >
                {t('webhooks.test')}
              </Button>
              <Button variant="secondary" onClick={() => openEdit(wh)} data-testid={`edit-webhook-${wh.id}`}>
                {t('common.edit')}
              </Button>
              <Button
                variant="danger"
                onClick={() => deleteMut.mutate(wh.id)}
                disabled={deleteMut.isPending}
                data-testid={`delete-webhook-${wh.id}`}
              >
                {t('common.delete')}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

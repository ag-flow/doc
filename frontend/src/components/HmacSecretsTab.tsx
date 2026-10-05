import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Key, Trash, Plus, Copy, Check } from '@phosphor-icons/react'
import { hmacSecretsApi, type HmacSecretOut } from '../lib/api'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Field } from './ui/field'
import { ConfirmDialog } from './ConfirmDialog'
import { EmptyState, TableSkeleton } from './ui/states'

const SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/

/** Onglet de gestion des secrets HMAC (générer / coller, copier, supprimer). */
export function HmacSecretsTab() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const { data: secrets = [], isLoading } = useQuery<HmacSecretOut[]>({
    queryKey: ['hmac-secrets'],
    queryFn: () => hmacSecretsApi.list(),
  })

  const [showForm, setShowForm] = useState(false)
  const [label, setLabel] = useState('')
  const [slug, setSlug] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [value, setValue] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [createdValue, setCreatedValue] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<HmacSecretOut | null>(null)

  const createMutation = useMutation({
    mutationFn: () => hmacSecretsApi.create({ label, slug, value: value.trim() || undefined }),
    onSuccess: (created) => {
      void qc.invalidateQueries({ queryKey: ['hmac-secrets'] })
      setCreatedValue(created.value)
      resetForm()
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => hmacSecretsApi.delete(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['hmac-secrets'] })
      setDeleteTarget(null)
    },
  })

  function resetForm() {
    setShowForm(false)
    setLabel('')
    setSlug('')
    setSlugTouched(false)
    setValue('')
    setFormError(null)
  }

  function handleLabel(v: string) {
    setLabel(v)
    setFormError(null)
    if (!slugTouched) {
      setSlug(v.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9_-]/g, '').replace(/^[-_]+/, ''))
    }
  }

  async function copyText(text: string, id: string) {
    try {
      await navigator.clipboard?.writeText(text)
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 1500)
    } catch {
      /* presse-papier indisponible : on ignore silencieusement */
    }
  }

  async function copyRow(s: HmacSecretOut) {
    const revealed = await hmacSecretsApi.reveal(s.id)
    await copyText(revealed.value, s.id)
  }

  const canSubmit = Boolean(label.trim()) && SLUG_RE.test(slug)

  if (isLoading) return <TableSkeleton rows={3} columns={3} />

  return (
    <>
      {createdValue && (
        <div
          className="mb-5 border-l-2 border-accent pl-4"
          data-testid="hmac-created-banner"
        >
          <p className="mb-2 text-[13px] font-[600] text-accent-700">{t('hmac.createdOnce')}</p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-md bg-neutral-100 px-3 py-2 text-xs [font-family:var(--font-mono)]">
              {createdValue}
            </code>
            <Button
              variant="icon"
              size="sm"
              onClick={() => copyText(createdValue, 'created')}
              title={t('hmac.copy')}
              data-testid="hmac-copy-created"
            >
              {copiedId === 'created'
                ? <Check size={15} weight="bold" className="text-accent-700" />
                : <Copy size={15} weight="duotone" />}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setCreatedValue(null)}>
              {t('common.close')}
            </Button>
          </div>
        </div>
      )}

      {secrets.length === 0 && !showForm && (
        <EmptyState testId="hmac-empty" message={t('hmac.empty')} />
      )}

      <ul className="m-0 list-none p-0">
        {secrets.map((s) => (
          <li
            key={s.id}
            className="flex items-center gap-3 border-b border-[var(--color-divider)] px-1 py-3"
            data-testid={`hmac-row-${s.slug}`}
          >
            <Key size={16} weight="duotone" className="shrink-0 text-accent-700" />
            <div className="min-w-0 flex-1">
              <p className="m-0 text-[15px] font-[600] [font-family:var(--font-heading)]">{s.label}</p>
              <p className="m-0 text-xs text-ink/[0.45] [font-family:var(--font-mono)]">{s.slug}</p>
            </div>
            <Button
              variant="icon"
              size="sm"
              onClick={() => copyRow(s)}
              title={t('hmac.copy')}
              data-testid={`hmac-copy-${s.slug}`}
            >
              {copiedId === s.id
                ? <Check size={15} weight="bold" className="text-accent-700" />
                : <Copy size={15} weight="duotone" />}
            </Button>
            <Button
              variant="icon"
              size="sm"
              className="text-accent-2-700"
              onClick={() => setDeleteTarget(s)}
              title={t('hmac.delete')}
              data-testid={`hmac-delete-${s.slug}`}
            >
              <Trash size={15} weight="duotone" />
            </Button>
          </li>
        ))}
      </ul>

      {showForm ? (
        <div className="mt-4 max-w-[560px] space-y-3.5">
          <div className="grid grid-cols-2 gap-3">
            <Field label={t('hmac.label')} htmlFor="hmac-label">
              <Input
                id="hmac-label"
                value={label}
                onChange={(e) => handleLabel(e.target.value)}
                placeholder="Workflow prod"
                data-testid="hmac-label-input"
              />
            </Field>
            <Field label={t('hmac.slug')} htmlFor="hmac-slug">
              <Input
                id="hmac-slug"
                value={slug}
                onChange={(e) => { setSlug(e.target.value); setSlugTouched(true); setFormError(null) }}
                placeholder="workflow-prod"
                data-testid="hmac-slug-input"
              />
            </Field>
          </div>
          <Field label={t('hmac.value')} htmlFor="hmac-value" hint={t('hmac.valueHint')}>
            <Input
              id="hmac-value"
              type="text"
              value={value}
              onChange={(e) => { setValue(e.target.value); setFormError(null) }}
              placeholder={t('hmac.valuePlaceholder')}
              data-testid="hmac-value-input"
            />
          </Field>
          <div aria-live="polite" className="empty:hidden">
            {formError && <p className="field-error m-0" data-testid="hmac-form-error">{formError}</p>}
          </div>
          <div className="flex gap-2">
            <Button
              onClick={() => createMutation.mutate()}
              disabled={!canSubmit || createMutation.isPending}
              data-testid="hmac-create-btn"
            >
              {createMutation.isPending
                ? t('common.loading')
                : value.trim()
                  ? t('hmac.add')
                  : t('hmac.addGenerate')}
            </Button>
            <Button variant="secondary" onClick={resetForm}>{t('common.cancel')}</Button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowForm(true)}
          className="mt-3 flex items-center gap-1.5 border-0 bg-transparent p-0 text-[13px] text-accent-700 hover:underline"
          data-testid="hmac-add-btn"
        >
          <Plus size={14} weight="duotone" />
          {t('hmac.addBtn')}
        </button>
      )}

      {deleteTarget && (
        <ConfirmDialog
          testId="hmac-delete-dialog"
          confirmTestId="hmac-delete-confirm-btn"
          title={t('hmac.deleteTitle')}
          message={t('hmac.deleteConfirm', { name: deleteTarget.label })}
          confirmLabel={t('common.delete')}
          pending={deleteMutation.isPending}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </>
  )
}

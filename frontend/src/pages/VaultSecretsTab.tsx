import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Check, Copy, Plus } from '@phosphor-icons/react'
import { secretsApi, type VaultSecretOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, TableSkeleton } from '../components/ui/states'
import { useToast } from '../components/Toast'

export function VaultSecretsTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: secrets = [], isLoading } = useQuery<VaultSecretOut[]>({
    queryKey: ['user-secrets'],
    queryFn: () => secretsApi.list(),
  })

  const [showForm, setShowForm] = useState(false)
  const [label, setLabel] = useState('')
  const [slug, setSlug] = useState('')
  const [value, setValue] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<VaultSecretOut | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () => secretsApi.create({ label, slug, value }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['user-secrets'] })
      resetForm()
    },
    onError: (err: Error) => setFormError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => secretsApi.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['user-secrets'] })
      setDeleteTarget(null)
      setDeleteError(null)
    },
    // 409 : le message porte la liste des automates concernés.
    onError: (err: Error) => setDeleteError(err.message),
  })

  // Dérive le slug automatiquement depuis le label si l'utilisateur n'a pas encore modifié le slug
  const [slugTouched, setSlugTouched] = useState(false)
  function handleLabelChange(v: string) {
    setLabel(v)
    setFormError(null)
    if (!slugTouched) {
      setSlug(v.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9_-]/g, '').replace(/^[-_]+/, ''))
    }
  }

  function resetForm() {
    setShowForm(false)
    setLabel('')
    setSlug('')
    setValue('')
    setSlugTouched(false)
    setFormError(null)
  }

  /** Copie la référence `${secret://…}` — JAMAIS la valeur (jamais relue). */
  function copyRef(s: VaultSecretOut) {
    void navigator.clipboard.writeText(secretsApi.refOf(s.id))
    setCopiedId(s.id)
    setTimeout(() => setCopiedId(null), 1500)
    toast(t('vault.refCopied'), 'success')
  }

  const canSubmit = label.trim() && /^[a-z0-9][a-z0-9_-]*$/.test(slug) && value.trim()

  if (isLoading) return <TableSkeleton rows={3} columns={4} />

  return (
    <>
      {secrets.length === 0 && !showForm ? (
        <EmptyState
          testId="secrets-empty"
          message={t('vault.secrets.empty')}
          action={
            <Button onClick={() => setShowForm(true)} data-testid="secret-add-btn">
              <Plus size={15} weight="duotone" /> {t('vault.secrets.addBtn')}
            </Button>
          }
        />
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>{t('vault.secrets.label')}</th>
                <th>{t('vault.colRef')}</th>
                <th>{t('vault.colUsedBy')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {secrets.map((s) => (
                <tr key={s.id} data-testid={`secret-row-${s.slug}`}>
                  <td>
                    <span className="text-[15px] font-[600] [font-family:var(--font-heading)]">
                      {s.label}
                    </span>
                    <span className="ml-2 text-[12px] text-ink/[0.45] [font-family:var(--font-mono)]">
                      {s.slug}
                    </span>
                  </td>
                  <td className="text-[12px] text-accent-700 [font-family:var(--font-mono)]">
                    {`\${secret://${s.id.slice(0, 8)}…}`}
                  </td>
                  <td className="text-ink/[0.55]" data-testid={`secret-usage-${s.slug}`}>
                    {s.used_by_automations + s.used_by_webhooks > 0
                      ? [
                          s.used_by_automations > 0
                            ? t('vault.usedByAutomations', { count: s.used_by_automations })
                            : null,
                          s.used_by_webhooks > 0
                            ? t('vault.usedByWebhooks', { count: s.used_by_webhooks })
                            : null,
                        ].filter(Boolean).join(' · ')
                      : t('vault.unused')}
                  </td>
                  <td className="whitespace-nowrap text-right">
                    <Button variant="icon" size="sm" title={t('vault.copyRef')}
                      aria-label={`${t('vault.copyRef')} ${s.label}`}
                      onClick={() => copyRef(s)}
                      data-testid={`secret-copy-${s.slug}`}>
                      {copiedId === s.id
                        ? <Check size={14} weight="bold" />
                        : <Copy size={14} weight="duotone" />}
                    </Button>
                    <Button variant="ghost" size="sm" className="text-accent-2-700"
                      onClick={() => { setDeleteTarget(s); setDeleteError(null) }}
                      aria-label={`${t('common.delete')} ${s.label}`}
                      data-testid={`secret-delete-${s.slug}`}>
                      {t('common.delete')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {!showForm && (
            <Button variant="ghost" size="sm" className="mt-3"
              onClick={() => setShowForm(true)} data-testid="secret-add-btn">
              <Plus size={13} weight="duotone" /> {t('vault.secrets.addBtn')}
            </Button>
          )}
        </>
      )}

      {showForm && (
        <form
          className="mt-5 flex max-w-xl flex-col gap-3"
          onSubmit={(e) => { e.preventDefault(); if (canSubmit) createMutation.mutate() }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t('vault.secrets.label')} htmlFor="secret-label">
              <Input
                id="secret-label"
                value={label}
                onChange={(e) => handleLabelChange(e.target.value)}
                placeholder="Ma clé API"
                autoFocus
                data-testid="secret-label-input"
              />
            </Field>
            <Field label={t('vault.secrets.slug')} htmlFor="secret-slug"
              hint={t('vault.secrets.slugHint')}>
              <Input
                id="secret-slug"
                value={slug}
                onChange={(e) => { setSlug(e.target.value); setSlugTouched(true); setFormError(null) }}
                placeholder="ma-cle-api"
                data-testid="secret-slug-input"
              />
            </Field>
          </div>
          {/* DoD : valeur masquée, écrite une fois, jamais relue depuis l'API. */}
          <Field label={t('vault.secrets.value')} htmlFor="secret-value">
            <Input
              id="secret-value"
              type="password"
              autoComplete="new-password"
              value={value}
              onChange={(e) => { setValue(e.target.value); setFormError(null) }}
              placeholder="••••••••••••"
              data-testid="secret-value-input"
            />
          </Field>
          <div aria-live="polite" className="empty:hidden">
            {formError && <p className="field-error m-0" data-testid="secret-form-error">{formError}</p>}
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={!canSubmit || createMutation.isPending}
              data-testid="secret-create-btn">
              {createMutation.isPending ? t('common.loading') : t('vault.secrets.add')}
            </Button>
            <Button type="button" variant="secondary" onClick={resetForm}>
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      )}

      {deleteTarget && (
        <ConfirmDialog
          testId="secret-delete-dialog"
          title={t('vault.secrets.deleteTitle')}
          message={t('vault.secrets.deleteConfirm', { name: deleteTarget.label })}
          impactMessage={
            deleteTarget.used_by_automations + deleteTarget.used_by_webhooks > 0
              ? [
                  deleteTarget.used_by_automations > 0
                    ? t('vault.usedByAutomations', { count: deleteTarget.used_by_automations })
                    : null,
                  deleteTarget.used_by_webhooks > 0
                    ? t('vault.usedByWebhooks', { count: deleteTarget.used_by_webhooks })
                    : null,
                ].filter(Boolean).join(' · ')
              : undefined
          }
          confirmLabel={t('common.delete')}
          confirmTestId="secret-delete-confirm-btn"
          pending={deleteMutation.isPending}
          error={deleteError}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => { setDeleteTarget(null); setDeleteError(null) }}
        />
      )}
    </>
  )
}

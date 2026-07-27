import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Plus } from '@phosphor-icons/react'
import { vaultApi, type VaultWalletOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, TableSkeleton } from '../components/ui/states'
import { relativeDate } from '../lib/relativeDate'

export function VaultWalletsTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const { data: wallets = [], isLoading } = useQuery<VaultWalletOut[]>({
    queryKey: ['vault-wallets'],
    queryFn: () => vaultApi.listWallets(),
    retry: false,
  })

  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<VaultWalletOut | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () => vaultApi.createWallet({ name, api_key: apiKey }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['vault-wallets'] })
      setShowForm(false)
      setName('')
      setApiKey('')
      setFormError(null)
    },
    onError: (err: Error) => setFormError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => vaultApi.deleteWallet(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['vault-wallets'] })
      setDeleteTarget(null)
      setDeleteError(null)
    },
    onError: (err: Error) => setDeleteError(err.message),
  })

  if (isLoading) return <TableSkeleton rows={3} columns={3} />

  return (
    <>
      {wallets.length === 0 && !showForm ? (
        <EmptyState
          testId="vault-empty"
          message={t('vault.empty')}
          action={
            <Button onClick={() => setShowForm(true)} data-testid="vault-add-btn">
              <Plus size={15} weight="duotone" /> {t('vault.addWallet')}
            </Button>
          }
        />
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>{t('vault.colWallet')}</th>
                <th>{t('vault.colRef')}</th>
                <th>{t('blocs.colLastWrite', 'Dernière écriture')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {wallets.map((w) => (
                <tr key={w.id} data-testid={`wallet-row-${w.name}`}>
                  <td className="text-[15px] font-[600] [font-family:var(--font-heading)]">
                    {w.name}
                  </td>
                  <td className="text-[12px] text-accent-700 [font-family:var(--font-mono)]">
                    {`\${vault://${w.name}:/…}`}
                  </td>
                  <td className="text-ink/[0.55]">{relativeDate(w.updated_at)}</td>
                  <td className="text-right">
                    <Button variant="ghost" size="sm" className="text-accent-2-700"
                      onClick={() => { setDeleteTarget(w); setDeleteError(null) }}
                      title={t('vault.delete')}
                      aria-label={`${t('vault.delete')} ${w.name}`}>
                      {t('common.delete')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {!showForm && (
            <Button variant="ghost" size="sm" className="mt-3"
              onClick={() => setShowForm(true)} data-testid="vault-add-btn">
              <Plus size={13} weight="duotone" /> {t('vault.addWallet')}
            </Button>
          )}
        </>
      )}

      {showForm && (
        <form
          className="mt-5 flex max-w-xl flex-col gap-3"
          onSubmit={(e) => { e.preventDefault(); if (name.trim() && apiKey.trim()) createMutation.mutate() }}
        >
          <Field label={t('vault.walletName')} htmlFor="wallet-name" hint={t('vault.walletNameHint')}>
            <Input
              id="wallet-name"
              value={name}
              onChange={(e) => { setName(e.target.value); setFormError(null) }}
              placeholder="mon-wallet"
              autoFocus
              data-testid="vault-name-input"
            />
          </Field>
          <Field label={t('vault.apiKey')} htmlFor="wallet-key">
            <Input
              id="wallet-key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => { setApiKey(e.target.value); setFormError(null) }}
              placeholder="••••••••••••"
              data-testid="vault-apikey-input"
            />
          </Field>
          <div aria-live="polite" className="empty:hidden">
            {formError && <p className="field-error m-0" data-testid="vault-form-error">{formError}</p>}
          </div>
          <div className="flex gap-2">
            <Button type="submit"
              disabled={!name.trim() || !apiKey.trim() || createMutation.isPending}
              data-testid="vault-create-btn">
              {createMutation.isPending ? t('common.loading') : t('vault.add')}
            </Button>
            <Button type="button" variant="secondary"
              onClick={() => { setShowForm(false); setFormError(null) }}>
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      )}

      {deleteTarget && (
        <ConfirmDialog
          testId="vault-delete-dialog"
          title={t('vault.deleteTitle')}
          message={t('vault.deleteConfirm', { name: deleteTarget.name })}
          confirmLabel={t('common.delete')}
          confirmTestId="vault-delete-confirm-btn"
          pending={deleteMutation.isPending}
          error={deleteError}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => { setDeleteTarget(null); setDeleteError(null) }}
        />
      )}
    </>
  )
}

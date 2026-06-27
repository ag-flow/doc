import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { KeyRound, Trash2, Plus } from 'lucide-react'
import { vaultApi, type VaultWalletOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

export function VaultAdmin() {
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

  if (isLoading) return <div className="p-8 text-gray-500">{t('common.loading')}</div>

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="mb-1 text-2xl font-semibold text-gray-900">{t('vault.title')}</h1>
      <p className="mb-6 text-sm text-gray-500">{t('vault.subtitle')}</p>

      {/* Liste des wallets */}
      <div className="rounded-lg border border-gray-200 bg-white divide-y divide-gray-100">
        {wallets.length === 0 && !showForm && (
          <p className="px-6 py-8 text-center text-sm text-gray-400">{t('vault.empty')}</p>
        )}

        {wallets.map((w) => (
          <div key={w.id} className="flex items-center gap-3 px-5 py-4">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-indigo-50 text-indigo-600 shrink-0">
              <KeyRound size={15} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-800">{w.name}</p>
              <p className="text-xs text-gray-400 font-mono">
                {`\${vault://${w.name}:/…}`}
              </p>
            </div>
            <button
              onClick={() => { setDeleteTarget(w); setDeleteError(null) }}
              className="rounded p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 transition-colors"
              title={t('vault.delete')}
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}

        {/* Formulaire d'ajout inline */}
        {showForm ? (
          <div className="px-5 py-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">
                  {t('vault.walletName')}
                </label>
                <Input
                  value={name}
                  onChange={(e) => { setName(e.target.value); setFormError(null) }}
                  placeholder="mon-wallet"
                  data-testid="vault-name-input"
                />
                <p className="mt-1 text-xs text-gray-400">{t('vault.walletNameHint')}</p>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600">
                  {t('vault.apiKey')}
                </label>
                <Input
                  type="password"
                  value={apiKey}
                  onChange={(e) => { setApiKey(e.target.value); setFormError(null) }}
                  placeholder="••••••••••••"
                  data-testid="vault-apikey-input"
                />
              </div>
            </div>
            {formError && (
              <p className="text-xs text-red-600" data-testid="vault-form-error">{formError}</p>
            )}
            <div className="flex gap-2">
              <Button
                onClick={() => createMutation.mutate()}
                disabled={!name.trim() || !apiKey.trim() || createMutation.isPending}
                data-testid="vault-create-btn"
              >
                {createMutation.isPending ? t('common.loading') : t('vault.add')}
              </Button>
              <Button variant="secondary" onClick={() => { setShowForm(false); setFormError(null) }}>
                {t('common.cancel')}
              </Button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowForm(true)}
            className="flex w-full items-center gap-2 px-5 py-3 text-sm text-indigo-600 hover:bg-indigo-50 transition-colors rounded-b-lg"
            data-testid="vault-add-btn"
          >
            <Plus size={15} />
            {t('vault.addWallet')}
          </button>
        )}
      </div>

      {/* Modale suppression */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-bold text-red-600">{t('vault.deleteTitle')}</h2>
            <p className="text-sm text-gray-600">
              {t('vault.deleteConfirm', { name: deleteTarget.name })}
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
                onClick={() => deleteMutation.mutate(deleteTarget.id)}
                disabled={deleteMutation.isPending}
                data-testid="vault-delete-confirm-btn"
              >
                {deleteMutation.isPending ? t('common.loading') : t('common.delete')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { isSuperAdmin } from '../lib/api'
import { VaultWalletsTab } from './VaultWalletsTab'
import { VaultSecretsTab } from './VaultSecretsTab'

type Tab = 'wallets' | 'secrets'

export function VaultAdmin() {
  const { t } = useTranslation()
  const superAdmin = isSuperAdmin()
  const [tab, setTab] = useState<Tab>(superAdmin ? 'wallets' : 'secrets')

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="mb-6 text-2xl font-semibold text-gray-900">{t('vault.title')}</h1>

      {/* Onglets */}
      <div className="mb-6 flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1">
        {superAdmin && (
          <button
            type="button"
            onClick={() => setTab('wallets')}
            className={[
              'flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors',
              tab === 'wallets'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700',
            ].join(' ')}
            data-testid="tab-wallets"
          >
            {t('vault.tabWallets')}
          </button>
        )}
        <button
          type="button"
          onClick={() => setTab('secrets')}
          className={[
            'flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors',
            tab === 'secrets'
              ? 'bg-white text-gray-900 shadow-sm'
              : 'text-gray-500 hover:text-gray-700',
          ].join(' ')}
          data-testid="tab-secrets"
        >
          {t('vault.tabSecrets')}
        </button>
      </div>

      {tab === 'wallets' && superAdmin && <VaultWalletsTab />}
      {tab === 'secrets' && <VaultSecretsTab />}
    </div>
  )
}

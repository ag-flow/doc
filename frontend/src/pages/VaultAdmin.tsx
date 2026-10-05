import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { isSuperAdmin } from '../lib/api'
import { SectionHead } from '../components/SectionHead'
import { VaultWalletsTab } from './VaultWalletsTab'
import { VaultSecretsTab } from './VaultSecretsTab'

type Tab = 'wallets' | 'secrets'

export function VaultAdmin() {
  const { t } = useTranslation()
  const superAdmin = isSuperAdmin()
  const [tab, setTab] = useState<Tab>(superAdmin ? 'wallets' : 'secrets')

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
    <div className="mx-auto max-w-[900px] px-6 pt-11 pb-24">
      <SectionHead kicker={t('vault.kicker')} title={t('vault.title')} />
      <p className="mb-6 max-w-[64ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        {t('vault.chapo')}
      </p>

      {/* Onglets à filet cyan */}
      <div className="mb-6 flex gap-1 border-b border-[var(--color-divider)]">
        {superAdmin && <TabBtn id="wallets">{t('vault.tabWallets')}</TabBtn>}
        <TabBtn id="secrets">{t('vault.tabSecrets')}</TabBtn>
      </div>

      {tab === 'wallets' && superAdmin && <VaultWalletsTab />}
      {tab === 'secrets' && <VaultSecretsTab />}
    </div>
  )
}

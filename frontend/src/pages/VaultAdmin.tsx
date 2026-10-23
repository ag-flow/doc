import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { isSuperAdmin } from '../lib/api'
import { SectionHead } from '../components/SectionHead'
import { VaultWalletsTab } from './VaultWalletsTab'
import { VaultSecretsTab } from './VaultSecretsTab'

type Tab = 'wallets' | 'secrets'

/** Clés i18n par issue de retour — un outcome inconnu retombe sur l'échec
 *  générique plutôt que de rester muet (le backend n'en envoie pas d'autre,
 *  mais une évolution côté backend ne doit jamais planter l'écran). */
const CONNECT_RESULT_KEY: Record<string, string> = {
  ok: 'vault.connectOk',
  denied: 'vault.connectDenied',
  invalid_state: 'vault.connectInvalidState',
  already: 'vault.connectAlready',
  duplicate: 'vault.connectDuplicate',
  error: 'vault.connectError',
}

export function VaultAdmin() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [connectMessage, setConnectMessage] =
    useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  // Lecture au montage uniquement : une fois le paramètre nettoyé plus bas,
  // un second passage de l'effet (StrictMode) ne doit pas rejouer le message.
  const connectHandledRef = useRef(false)

  useEffect(() => {
    if (connectHandledRef.current) return
    connectHandledRef.current = true
    const outcome = searchParams.get('connect')
    if (!outcome) return

    const key = CONNECT_RESULT_KEY[outcome] ?? CONNECT_RESULT_KEY.error
    setConnectMessage({ kind: outcome === 'ok' ? 'success' : 'error', text: t(key) })
    if (outcome === 'ok') {
      // Le nouvel endpoint ET le nouveau secret local apparaissent ensemble.
      void queryClient.invalidateQueries({ queryKey: ['vault-wallets'] })
      void queryClient.invalidateQueries({ queryKey: ['harpocrate-keys'] })
    }

    const next = new URLSearchParams(searchParams)
    next.delete('connect')
    setSearchParams(next, { replace: true })
    // Lecture volontairement figée au montage (voir connectHandledRef) :
    // dépendances omises pour ne jamais rejouer sur un changement d'URL.
  }, [])

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

      {connectMessage && (
        <div
          role="status"
          className={`mb-6 max-w-xl rounded-md border px-4 py-2 text-[14px] ${
            connectMessage.kind === 'success'
              ? 'border-accent-700/30 bg-accent-700/10 text-accent-700'
              : 'border-accent-2-700/30 bg-accent-2-700/10 text-accent-2-700'
          }`}
          data-testid="vault-connect-message"
        >
          {connectMessage.text}
        </div>
      )}

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

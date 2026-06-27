import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { oidcApi, type OidcConfigOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

export function OidcAdmin() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const { data: config, isLoading, isError, error } = useQuery<OidcConfigOut | null>({
    queryKey: ['oidc-config'],
    queryFn: () => oidcApi.get(),
    retry: false,
  })

  const [issuer, setIssuer] = useState('')
  const [clientId, setClientId] = useState('')
  const [secretRef, setSecretRef] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (config) {
      setIssuer(config.issuer)
      setClientId(config.client_id)
      setEnabled(config.enabled)
    }
  }, [config])

  const saveMutation = useMutation({
    mutationFn: () =>
      oidcApi.set({ issuer, client_id: clientId, client_secret_ref: secretRef, enabled }),
    onSuccess: (updated) => {
      void queryClient.setQueryData(['oidc-config'], updated)
      setSaveMsg(t('oidc.saved'))
      setSaveError(null)
      setSecretRef('')
    },
    onError: (err: Error) => {
      setSaveError(err.message)
      setSaveMsg(null)
    },
  })

  if (isLoading) return <div className="p-8 text-gray-500">{t('common.loading')}</div>

  if (isError) {
    const status = (error as { status?: number }).status
    if (status === 403) {
      return <div className="p-8 text-red-600">{t('oidc.forbidden')}</div>
    }
  }

  const hasExistingConfig = Boolean(config)
  const canSave = issuer.trim() && clientId.trim() && secretRef.trim()

  return (
    <div className="p-8 max-w-lg">
      <h1 className="mb-1 text-2xl font-semibold text-gray-900">{t('oidc.title')}</h1>
      <p className="mb-6 text-sm text-gray-500">{t('oidc.subtitle')}</p>

      <div className="space-y-5 rounded-lg border border-gray-200 bg-white p-6">
        {/* Issuer */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">{t('oidc.issuer')}</label>
          <Input
            value={issuer}
            onChange={(e) => { setIssuer(e.target.value); setSaveMsg(null) }}
            placeholder="https://security.yoops.org/realms/yoops"
            data-testid="oidc-issuer"
          />
          <p className="mt-1 text-xs text-gray-400">{t('oidc.issuerHint')}</p>
        </div>

        {/* Client ID */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">{t('oidc.clientId')}</label>
          <Input
            value={clientId}
            onChange={(e) => { setClientId(e.target.value); setSaveMsg(null) }}
            placeholder="docflow"
            data-testid="oidc-client-id"
          />
        </div>

        {/* Secret ref */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">{t('oidc.secretRef')}</label>
          <Input
            value={secretRef}
            onChange={(e) => { setSecretRef(e.target.value); setSaveMsg(null) }}
            placeholder="${vault://docflow/oidc_client_secret}"
            data-testid="oidc-secret-ref"
          />
          <p className="mt-1 text-xs text-gray-400">
            {hasExistingConfig ? t('oidc.secretRefMasked') : t('oidc.secretRefHint')}
          </p>
        </div>

        {/* Enabled toggle */}
        <div className="flex items-center gap-3">
          <button
            role="switch"
            aria-checked={enabled}
            onClick={() => { setEnabled((v) => !v); setSaveMsg(null) }}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              enabled ? 'bg-indigo-600' : 'bg-gray-200'
            }`}
            data-testid="oidc-enabled-toggle"
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                enabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
          <span className="text-sm text-gray-700">
            {enabled ? t('oidc.enabledOn') : t('oidc.enabledOff')}
          </span>
        </div>

        {saveMsg && (
          <p className="rounded-lg border border-green-200 bg-green-50 px-4 py-2 text-sm text-green-700"
            data-testid="oidc-save-msg">
            {saveMsg}
          </p>
        )}
        {saveError && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700"
            data-testid="oidc-save-error">
            {saveError}
          </p>
        )}

        <div className="flex items-center gap-3 pt-2">
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={!canSave || saveMutation.isPending}
            data-testid="oidc-save-btn"
          >
            {saveMutation.isPending ? t('common.loading') : t('common.save')}
          </Button>
          {!canSave && (
            <span className="text-xs text-gray-400">{t('oidc.secretRequired')}</span>
          )}
        </div>
      </div>

      {hasExistingConfig && config && (
        <p className="mt-4 text-xs text-gray-400">
          {t('oidc.lastUpdated', { date: new Date(config.updated_at).toLocaleString('fr-FR') })}
        </p>
      )}
    </div>
  )
}

import { useEffect, useState, type ReactNode } from 'react'
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
    <div className="p-8 max-w-2xl">
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

      <KeycloakGuide />
    </div>
  )
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-4">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700">
        {n}
      </div>
      <div className="min-w-0">
        <p className="mb-1 text-sm font-medium text-gray-800">{title}</p>
        <div className="text-sm text-gray-600">{children}</div>
      </div>
    </div>
  )
}

function Code({ children }: { children: string | ReactNode }) {
  return (
    <code className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs text-gray-800">
      {children}
    </code>
  )
}

function Block({ children }: { children: string }) {
  return (
    <pre className="mt-1.5 overflow-x-auto rounded-md bg-gray-900 px-4 py-3 font-mono text-xs text-gray-100">
      {children}
    </pre>
  )
}

function KeycloakGuide() {
  return (
    <details className="mt-8 rounded-lg border border-gray-200 bg-white" open>
      <summary className="cursor-pointer select-none px-6 py-4 text-sm font-semibold text-gray-800 hover:bg-gray-50">
        Procédure — Créer le client Keycloak
      </summary>

      <div className="space-y-6 px-6 pb-6 pt-4">
        <Step n={1} title="Ouvrir la console d'administration Keycloak">
          <p>
            Connectez-vous sur{' '}
            <a
              href="https://security.yoops.org"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-600 underline"
            >
              https://security.yoops.org
            </a>{' '}
            avec un compte admin. Sélectionnez le realm <Code>yoops</Code> dans le menu
            déroulant en haut à gauche.
          </p>
        </Step>

        <Step n={2} title="Créer le client">
          <p>
            <strong>Clients</strong> → <strong>Create client</strong>.
          </p>
          <ul className="mt-2 list-inside list-disc space-y-1">
            <li>Client type : <Code>OpenID Connect</Code></li>
            <li>Client ID : <Code>docflow</Code></li>
            <li>Name : <Code>docflow</Code> (optionnel)</li>
          </ul>
          <p className="mt-2">Cliquez <strong>Next</strong>.</p>
        </Step>

        <Step n={3} title="Activer l'authentification client (confidential)">
          <p>
            Dans l'onglet <strong>Capability config</strong> :
          </p>
          <ul className="mt-2 list-inside list-disc space-y-1">
            <li>
              <strong>Client authentication</strong> → <Code>On</Code>{' '}
              <span className="text-gray-400">(génère un client secret)</span>
            </li>
            <li>
              <strong>Direct access grants</strong> → <Code>Off</Code>{' '}
              <span className="text-gray-400">(désactivé, on utilise le code flow)</span>
            </li>
          </ul>
          <p className="mt-2">Cliquez <strong>Next</strong>.</p>
        </Step>

        <Step n={4} title="Configurer les URLs">
          <p>Dans <strong>Login settings</strong> :</p>
          <ul className="mt-2 list-inside list-disc space-y-1">
            <li>
              Valid redirect URIs :{' '}
              <Code>https://docflow.yoops.org/*</Code>
            </li>
            <li>
              Web origins :{' '}
              <Code>https://docflow.yoops.org</Code>
            </li>
          </ul>
          <p className="mt-2">
            Ajoutez aussi <Code>http://localhost:5173/*</Code> pour le développement local.
          </p>
          <p className="mt-2">Cliquez <strong>Save</strong>.</p>
        </Step>

        <Step n={5} title="Récupérer le client secret">
          <p>
            Dans la fiche du client, onglet <strong>Credentials</strong>.
            Copiez la valeur du champ <strong>Client secret</strong>.
          </p>
        </Step>

        <Step n={6} title="Stocker le secret dans Harpocrate">
          <p>
            Sur le serveur hébergeant docflow (ou via l'API Harpocrate), écrivez le secret :
          </p>
          <Block>{'harpocrate put docflow/oidc_client_secret <votre-secret>'}</Block>
          <p className="mt-2">
            La référence vault à utiliser dans le formulaire ci-dessus sera :
          </p>
          <Block>{'${vault://docflow/oidc_client_secret}'}</Block>
        </Step>

        <Step n={7} title="Remplir et enregistrer le formulaire">
          <ul className="list-inside list-disc space-y-1">
            <li>
              Issuer :{' '}
              <Code>https://security.yoops.org/realms/yoops</Code>
            </li>
            <li>Client ID : <Code>docflow</Code></li>
            <li>Référence vault : valeur copiée à l'étape 6</li>
            <li>
              Activez le toggle <strong>OIDC activé</strong> une fois les tests de connexion
              validés.
            </li>
          </ul>
        </Step>

        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <strong>Break-glass :</strong> le compte admin local reste opérationnel même avec
          l'OIDC activé. En cas de panne Keycloak, connectez-vous via{' '}
          <Code>POST /api/auth/login</Code> avec les identifiants bootstrap.
        </div>
      </div>
    </details>
  )
}

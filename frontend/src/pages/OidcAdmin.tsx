import { useEffect, useState, type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { type AuthMethodsOut, oidcApi, setupApi, type OidcConfigOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { SecretInput } from '../components/SecretInput'
import { SectionHead } from '../components/SectionHead'
import { ErrorLine, SheetSkeleton } from '../components/ui/states'

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
  const [disableLocal, setDisableLocal] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (config) {
      setIssuer(config.issuer)
      setClientId(config.client_id)
      setEnabled(config.enabled)
      setDisableLocal(config.disable_local_login)
    }
  }, [config])

  const saveMutation = useMutation({
    mutationFn: () =>
      oidcApi.set({ issuer, client_id: clientId, client_secret_ref: secretRef, enabled, disable_local_login: disableLocal }),
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

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
        <SheetSkeleton />
      </div>
    )
  }

  if (isError) {
    const status = (error as { status?: number }).status
    if (status === 403) {
      return (
        <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
          <ErrorLine message={t('oidc.forbidden')} />
        </div>
      )
    }
  }

  const hasExistingConfig = Boolean(config)
  const canSave = issuer.trim() && clientId.trim() && secretRef.trim()

  return (
    <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
      <SectionHead kicker="Administration" title={t('oidc.title')} />
      <p className="mb-8 max-w-[96ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        {t('oidc.subtitle')}
      </p>

      <LocalLoginFlag />

      <div className="max-w-[560px] space-y-6">
        {/* Issuer */}
        <div className="field">
          <label htmlFor="oidc-issuer">{t('oidc.issuer')}</label>
          <Input
            id="oidc-issuer"
            value={issuer}
            onChange={(e) => { setIssuer(e.target.value); setSaveMsg(null) }}
            placeholder="https://security.yoops.org/realms/yoops"
            data-testid="oidc-issuer"
          />
          <p className="field-hint m-0">{t('oidc.issuerHint')}</p>
        </div>

        {/* Client ID */}
        <div className="field">
          <label htmlFor="oidc-client-id">{t('oidc.clientId')}</label>
          <Input
            id="oidc-client-id"
            value={clientId}
            onChange={(e) => { setClientId(e.target.value); setSaveMsg(null) }}
            placeholder="docflow"
            data-testid="oidc-client-id"
          />
        </div>

        {/* Secret ref */}
        <div className="field">
          <label>{t('oidc.secretRef')}</label>
          <SecretInput
            value={secretRef}
            onChange={(v) => { setSecretRef(v); setSaveMsg(null) }}
            placeholder={t('oidc.secretRefPlaceholder')}
          />
          {hasExistingConfig && (
            <p className="field-hint m-0">{t('oidc.secretRefMasked')}</p>
          )}
        </div>

        {/* Enabled toggle */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            onClick={() => { setEnabled((v) => !v); setSaveMsg(null) }}
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border-0 transition-colors ${
              enabled ? 'bg-accent' : 'bg-neutral-300'
            }`}
            data-testid="oidc-enabled-toggle"
          >
            <span
              className={`inline-block h-3.5 w-3.5 transform rounded-full bg-paper shadow-sm transition-transform ${
                enabled ? 'translate-x-[18px]' : 'translate-x-0.5'
              }`}
            />
          </button>
          <span className="text-[14px]">
            {enabled ? t('oidc.enabledOn') : t('oidc.enabledOff')}
          </span>
        </div>

        {/* Mode OIDC-only */}
        <label className="flex items-start gap-2 text-[14px]">
          <input
            type="checkbox"
            className="mt-1"
            checked={disableLocal}
            onChange={(e) => { setDisableLocal(e.target.checked); setSaveMsg(null) }}
            data-testid="oidc-disable-local"
          />
          <span>
            Désactiver la connexion locale (mode OIDC-only).
            <span className="block text-[12px] leading-[1.6] text-ink/[0.55]">
              Sans effet tant que l'OIDC n'est pas activé — et désactiver l'OIDC
              réactive automatiquement la connexion locale. En cas de panne :
              surcharge <span className="[font-family:var(--font-mono)]">LOCAL_LOGIN_ENABLED=true</span>{' '}
              dans <span className="[font-family:var(--font-mono)]">/data/.env</span> + redémarrage.
            </span>
          </span>
        </label>

        <div aria-live="polite" className="empty:hidden">
          {saveMsg && (
            <p className="m-0 text-[14px] text-accent-700" data-testid="oidc-save-msg">
              {saveMsg}
            </p>
          )}
          {saveError && (
            <p className="m-0 text-[14px] text-accent-2-700" data-testid="oidc-save-error">
              {saveError}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={!canSave || saveMutation.isPending}
            data-testid="oidc-save-btn"
          >
            {saveMutation.isPending ? t('common.loading') : t('common.save')}
          </Button>
          {!canSave && (
            <span className="text-[12px] text-ink/[0.5]">{t('oidc.secretRequired')}</span>
          )}
        </div>
      </div>

      {hasExistingConfig && config && (
        <p className="mt-4 text-[12px] text-ink/[0.5]">
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
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-100 text-[12px] font-[600] text-accent-800">
        {n}
      </div>
      <div className="min-w-0">
        <p className="mb-1 text-[15px] font-[600] [font-family:var(--font-heading)]">{title}</p>
        <div className="text-[14px] leading-[1.6] text-ink/[0.7]">{children}</div>
      </div>
    </div>
  )
}

function Code({ children }: { children: string | ReactNode }) {
  return (
    <code className="rounded-sm bg-neutral-100 px-1.5 py-0.5 text-[12px] [font-family:var(--font-mono)]">
      {children}
    </code>
  )
}

function Block({ children }: { children: string }) {
  return (
    <pre className="mt-1.5 overflow-x-auto rounded-md bg-neutral-900 px-4 py-3 text-[12px] text-neutral-100 [font-family:var(--font-mono)]">
      {children}
    </pre>
  )
}

function KeycloakGuide() {
  return (
    <details className="mt-14" open>
      <summary className="cursor-pointer select-none text-[11px] font-[600] uppercase tracking-[0.08em] text-ink/[0.5] hover:text-accent-700">
        Procédure — Créer le client Keycloak
      </summary>

      <div className="mt-5 max-w-[720px] space-y-6 border-t border-[var(--color-divider)] pt-5">
        <Step n={1} title="Ouvrir la console d'administration Keycloak">
          <p>
            Connectez-vous sur{' '}
            <a
              href="https://security.yoops.org"
              target="_blank"
              rel="noreferrer"
              className="text-accent-700 underline"
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
              <span className="text-ink/[0.5]">(génère un client secret)</span>
            </li>
            <li>
              <strong>Direct access grants</strong> → <Code>Off</Code>{' '}
              <span className="text-ink/[0.5]">(désactivé, on utilise le code flow)</span>
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

        <div className="border-l-2 border-accent pl-4 text-[14px] leading-[1.6] text-ink/[0.7]">
          <strong>Break-glass :</strong> le compte admin local reste opérationnel même avec
          l'OIDC activé. En cas de panne Keycloak, connectez-vous via{' '}
          <Code>POST /api/auth/login</Code> avec les identifiants bootstrap.
        </div>
      </div>
    </details>
  )
}


/** État du break-glass LOCAL_LOGIN_ENABLED — lecture seule : le flag vit dans
 *  /data/.env (volontairement hors base) pour rester actionnable même quand
 *  l'OIDC est en panne. */
function LocalLoginFlag() {
  const { data } = useQuery<AuthMethodsOut>({
    queryKey: ['auth-methods'],
    queryFn: () => setupApi.methods(),
  })
  if (!data) return null
  return (
    <div
      className={`mb-8 max-w-[560px] border-l-2 pl-4 text-[14px] ${data.local
        ? 'border-[var(--color-divider)] text-ink/[0.65]'
        : 'border-accent-2 text-accent-2-700'}`}
      data-testid="local-login-flag"
    >
      <p className="m-0 font-[600] [font-family:var(--font-heading)]">
        Connexion locale : {data.local ? 'activée' : 'désactivée (mode OIDC-only)'}
      </p>
      <p className={`m-0 mt-1 text-[12px] leading-[1.6] ${data.local ? 'text-ink/[0.55]' : ''}`}>
        Piloté par la case « mode OIDC-only » ci-dessous (effective seulement
        quand l'OIDC est activé). Surcharge break-glass possible :{' '}
        <span className="[font-family:var(--font-mono)]">LOCAL_LOGIN_ENABLED=true</span> dans{' '}
        <span className="[font-family:var(--font-mono)]">/data/.env</span> + redémarrage force le
        retour de la connexion locale en cas de panne OIDC.
      </p>
    </div>
  )
}

import { type FormEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation, Trans } from 'react-i18next'
import { GithubLogo } from '@phosphor-icons/react'
import { api, setToken, setupApi } from '../lib/api'
import { beginOidcLogin } from '../lib/oidcClient'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { SetupForm } from '../components/SetupForm'

/** Surtitre en petites capitales cyan — le seul « titre » au-dessus d'un pilier. */
function Kicker({ children, magenta = false }: { children: string; magenta?: boolean }) {
  return (
    <div
      className={`text-[11px] uppercase tracking-[0.1em] ${
        magenta ? 'text-accent-2-700' : 'text-accent-700'
      }`}
    >
      {children}
    </div>
  )
}

function Pillar({ title, body, magenta = false }: { title: string; body: string; magenta?: boolean }) {
  return (
    <div>
      <Kicker magenta={magenta}>{title}</Kicker>
      <p className="m-0 mt-1.5 text-[15px] leading-[1.55] text-ink/[0.72]">{body}</p>
    </div>
  )
}

export function Login() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pendingValidation, setPendingValidation] = useState(false)
  const [loading, setLoading] = useState(false)
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null)
  const [oidcAvailable, setOidcAvailable] = useState(false)
  const [localEnabled, setLocalEnabled] = useState(true)
  const [oidcLoading, setOidcLoading] = useState(false)

  useEffect(() => {
    setupApi
      .methods()
      .then((m) => {
        setOidcAvailable(m.oidc)
        setLocalEnabled(m.local)
        setNeedsSetup(m.needs_setup)
      })
      .catch(() => setNeedsSetup(false))
  }, [])

  async function handleOidcLogin() {
    setError(null)
    setPendingValidation(false)
    setOidcLoading(true)
    try {
      await beginOidcLogin() // redirige vers l'issuer — pas de retour en cas de succès
    } catch {
      setError(t('login.oidcError'))
      setOidcLoading(false)
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setPendingValidation(false)
    setLoading(true)
    try {
      const res = await api.post<{ access_token: string }>('/auth/login', { email, password })
      setToken(res.access_token)
      navigate('/')
    } catch (err: unknown) {
      const detail = (err as { detail?: string }).detail
      if (detail === 'PendingValidation') {
        setPendingValidation(true)
      } else {
        setError(t('login.error'))
      }
    } finally {
      setLoading(false)
    }
  }

  // Attendre la réponse de /auth/methods avant d'afficher quoi que ce soit
  if (needsSetup === null) return null

  if (needsSetup) return <SetupForm />

  return (
    <div className="grid min-h-screen bg-paper lg:grid-cols-[1.15fr_minmax(360px,0.85fr)]">
      {/* ── Colonne éditoriale : la marque tient la page, pas une carte ── */}
      <section className="hidden flex-col px-[52px] pt-11 pb-8 lg:flex">
        <Kicker>{t('login.kicker')}</Kicker>
        {/* Tête de journal : filet gras puis filet fin. */}
        <div className="mt-3.5 h-1 bg-ink" />
        <div className="mt-[3px] h-px bg-ink" />

        <h1 className="mt-[22px] text-[clamp(64px,7vw,104px)] leading-[0.92] tracking-[-0.03em]">
          docflow
        </h1>
        <p className="mt-[22px] max-w-[34ch] text-[20px] leading-[1.5] text-ink/[0.78]">
          <Trans i18nKey="login.hook" components={{ em: <em /> }} />
        </p>

        <div className="mt-8 grid max-w-[640px] gap-x-10 gap-y-[22px] sm:grid-cols-2">
          <Pillar title={t('login.pillars.writeTitle')} body={t('login.pillars.writeBody')} />
          <Pillar title={t('login.pillars.structureTitle')} body={t('login.pillars.structureBody')} />
          <Pillar title={t('login.pillars.operateTitle')} body={t('login.pillars.operateBody')} />
          <Pillar title={t('login.pillars.agentsTitle')} body={t('login.pillars.agentsBody')} magenta />
        </div>

        <div className="flex-1" />

        <div className="mt-8 max-w-[640px]">
          <Kicker magenta>{t('login.suiteTitle')}</Kicker>
          <div className="mt-2.5 grid gap-x-11 gap-y-[22px] sm:grid-cols-2">
            {(['workflow', 'ragflow'] as const).map((tool) => (
              <div key={tool}>
                <h5 className="mb-1">{tool}</h5>
                <p className="m-0 text-[14px] leading-[1.5] text-ink/[0.68]">
                  {t(`login.suite.${tool}Body`)}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-6 border-t border-[var(--color-divider)] pt-3 text-[12px] text-ink/[0.55]">
          <a
            href="https://github.com/ag-flow"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-[13px] no-underline"
          >
            <GithubLogo size={16} weight="duotone" />
            github.com/ag-flow
          </a>
          <span className="flex-1" />
          <span>{t('login.stack')}</span>
        </div>
      </section>

      {/* ── Colonne formulaire ── */}
      <section className="flex items-center justify-center bg-surface px-[52px] pt-11 pb-8">
        <div className="w-full max-w-[340px]">
          <h3 className="mb-1">{t('login.formTitle')}</h3>
          <p className="mb-6 text-[13px] text-ink/[0.6]">{t('login.formHint')}</p>

          {!localEnabled && (
            <p className="mb-5 text-[13px] text-ink/[0.7]" data-testid="local-disabled-notice">
              {t('login.localDisabled')}
            </p>
          )}

          {localEnabled && (
            <form onSubmit={handleSubmit} className="grid gap-3.5">
              <Field label={t('login.email')} htmlFor="login-email">
                <Input
                  id="login-email"
                  type="email"
                  className="bg-paper"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  data-testid="email-input"
                />
              </Field>
              {/* L'erreur d'authentification porte sur le couple : elle s'affiche
                  sous le mot de passe, en magenta, sans encadré. */}
              <Field label={t('login.password')} htmlFor="login-password" error={error}>
                <Input
                  id="login-password"
                  type="password"
                  className="bg-paper"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  aria-invalid={error ? 'true' : undefined}
                  data-testid="password-input"
                />
              </Field>
              <Button type="submit" block disabled={loading} data-testid="submit-button">
                {t('login.submit')}
              </Button>
            </form>
          )}

          {/* Annonce des états d'authentification aux lecteurs d'écran : la
              région existe en permanence, sinon son apparition n'est pas lue. */}
          <div aria-live="polite" className="mt-2.5 empty:mt-0">
            {pendingValidation && (
              <p className="text-[13px] text-ink/[0.7]" data-testid="pending-validation">
                {t('login.pendingValidation')}
              </p>
            )}
          </div>

          {oidcAvailable && (
            /* Séparé par du blanc — pas de filet « ou ». */
            <div className="mt-6">
              <Button
                type="button"
                variant="secondary"
                block
                disabled={oidcLoading}
                onClick={handleOidcLogin}
                data-testid="oidc-button"
              >
                {oidcLoading ? t('login.oidcLoading') : t('login.oidc')}
              </Button>
            </div>
          )}

          <p className="mt-6 text-[12px] text-ink/[0.55]">{t('login.setupHint')}</p>
        </div>
      </section>
    </div>
  )
}

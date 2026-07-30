import { useEffect, useState, type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  eventsProducerApi,
  hmacSecretsApi,
  type EventCatalog,
  type EventsProducerConfigOut,
  type HmacSecretOut,
} from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { SectionHead } from '../components/SectionHead'
import { ErrorLine, TableSkeleton } from '../components/ui/states'

export function EventsProducerAdmin() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const { data: config, isLoading, isError, error } = useQuery<EventsProducerConfigOut>({
    queryKey: ['events-producer-config'],
    queryFn: () => eventsProducerApi.get(),
    retry: false,
  })
  const { data: catalog, isError: catalogError } = useQuery<EventCatalog>({
    queryKey: ['events-catalog'],
    queryFn: () => eventsProducerApi.catalog(),
    retry: false,
  })
  const { data: hmacSecrets = [] } = useQuery<HmacSecretOut[]>({
    queryKey: ['hmac-secrets'],
    queryFn: () => hmacSecretsApi.list(),
    retry: false,
  })

  const [enabled, setEnabled] = useState(false)
  const [ingestionUrl, setIngestionUrl] = useState('')
  const [sourceUri, setSourceUri] = useState('')
  const [selectedSecretId, setSelectedSecretId] = useState('')
  const [allowed, setAllowed] = useState<string[]>([])
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ status: number; ok: boolean } | null>(null)
  const [testError, setTestError] = useState<string | null>(null)

  useEffect(() => {
    if (config) {
      setEnabled(config.enabled)
      setIngestionUrl(config.ingestion_url ?? '')
      setSourceUri(config.source_uri)
      setAllowed(config.allowed_events)
    }
  }, [config])

  const secretConfigured = Boolean(config?.secret_configured) || Boolean(selectedSecretId)

  const saveMutation = useMutation({
    mutationFn: () => {
      const body = {
        enabled,
        ingestion_url: ingestionUrl.trim() || null,
        source_uri: sourceUri.trim() || 'docflow',
        allowed_events: allowed,
        ...(selectedSecretId ? { secret_ref: `\${hmac://${selectedSecretId}}` } : {}),
      }
      return eventsProducerApi.update(body)
    },
    onSuccess: (updated) => {
      void queryClient.setQueryData(['events-producer-config'], updated)
      setSaveMsg(t('eventsProducer.saved'))
      setSaveError(null)
      setSelectedSecretId('')
    },
    onError: (err: Error) => {
      setSaveError(err.message)
      setSaveMsg(null)
    },
  })

  const testMutation = useMutation({
    mutationFn: () => eventsProducerApi.testConnection(),
    onSuccess: (res) => {
      setTestResult(res)
      setTestError(null)
    },
    onError: (err: Error) => {
      const status = (err as { status?: number }).status
      setTestError(status === 400 ? t('eventsProducer.testIncomplete') : err.message)
      setTestResult(null)
    },
  })

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
        <SectionHead kicker="Administration" title={t('eventsProducer.title')} />
        <TableSkeleton rows={4} columns={2} />
      </div>
    )
  }
  if (isError && (error as { status?: number }).status === 403) {
    return (
      <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
        <SectionHead kicker="Administration" title={t('eventsProducer.title')} />
        <ErrorLine message={t('eventsProducer.forbidden')} />
      </div>
    )
  }

  function toggleEvent(code: string) {
    setSaveMsg(null)
    setAllowed((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]))
  }

  const events = catalog?.events ?? []
  const canTest = Boolean(ingestionUrl.trim() && secretConfigured)

  return (
    <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
      <SectionHead kicker="Administration" title={t('eventsProducer.title')} />
      <p className="mb-8 max-w-[96ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        {t('eventsProducer.subtitle')}
      </p>

      <section className="max-w-[640px] space-y-5">
        {/* URL d'ingestion */}
        <Field label={t('eventsProducer.ingestionUrl')} hint={t('eventsProducer.ingestionUrlHint')}
          htmlFor="ep-ingestion-url">
          <Input
            id="ep-ingestion-url"
            value={ingestionUrl}
            onChange={(e) => { setIngestionUrl(e.target.value); setSaveMsg(null) }}
            placeholder="https://workflow.yoops.org"
            data-testid="ep-ingestion-url"
          />
        </Field>

        {/* source_uri */}
        <Field label={t('eventsProducer.sourceUri')} hint={t('eventsProducer.sourceUriHint')}
          htmlFor="ep-source-uri">
          <Input
            id="ep-source-uri"
            value={sourceUri}
            onChange={(e) => { setSourceUri(e.target.value); setSaveMsg(null) }}
            placeholder="docflow"
            data-testid="ep-source-uri"
          />
        </Field>

        {/* Secret HMAC — sélection parmi les secrets gérés (onglet HMAC des Clés API) */}
        <div className="field">
          <label htmlFor="ep-secret-select">{t('eventsProducer.secretRef')}</label>
          <select
            id="ep-secret-select"
            value={selectedSecretId}
            onChange={(e) => { setSelectedSecretId(e.target.value); setSaveMsg(null) }}
            data-testid="ep-secret-select"
            className="input"
          >
            <option value="">
              {config?.secret_configured
                ? t('eventsProducer.secretKeepCurrent')
                : t('eventsProducer.secretChoose')}
            </option>
            {hmacSecrets.map((s) => (
              <option key={s.id} value={s.id}>{s.label} ({s.slug})</option>
            ))}
          </select>
          <p className={`mt-1 text-[11px] ${config?.secret_configured || selectedSecretId ? 'text-accent-700' : 'text-accent-2-700'}`}>
            {config?.secret_configured || selectedSecretId
              ? t('eventsProducer.secretConfigured')
              : t('eventsProducer.secretMissing')}
          </p>
          <a href="/api-keys" className="mt-1 inline-block text-[12px] text-accent-700 hover:underline">
            {t('eventsProducer.manageHmac')}
          </a>
        </div>

        {/* Events autorisés */}
        <div className="field">
          <label>{t('eventsProducer.allowedEvents')}</label>
          <p className="mb-2 text-[11px] text-ink/[0.55]">{t('eventsProducer.allowedEventsHint')}</p>
          {catalogError ? (
            <p className="text-[14px] text-accent-2-700">{t('eventsProducer.catalogError')}</p>
          ) : (
            <>
              <div className="mb-2 flex gap-3 text-[12px]">
                <button
                  type="button"
                  className="border-0 bg-transparent p-0 text-accent-700 hover:underline"
                  onClick={() => { setAllowed(events.map((e) => e.eventCode)); setSaveMsg(null) }}
                >
                  {t('eventsProducer.selectAll')}
                </button>
                <button
                  type="button"
                  className="border-0 bg-transparent p-0 text-accent-700 hover:underline"
                  onClick={() => { setAllowed([]); setSaveMsg(null) }}
                >
                  {t('eventsProducer.selectNone')}
                </button>
              </div>
              <div className="space-y-1.5">
                {events.map((ev) => (
                  <label key={ev.eventCode} className="flex items-start gap-2 text-[14px]">
                    <input
                      type="checkbox"
                      className="mt-0.5 accent-[var(--color-accent)]"
                      checked={allowed.includes(ev.eventCode)}
                      onChange={() => toggleEvent(ev.eventCode)}
                      data-testid={`ep-event-${ev.eventCode}`}
                    />
                    <span>
                      <span className="text-[12px] text-ink/[0.85] [font-family:var(--font-mono)]">
                        {ev.eventCode}
                      </span>
                      <span className="block text-[12px] text-ink/[0.55]">{ev.title}</span>
                    </span>
                  </label>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Toggle activé */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            onClick={() => { setEnabled((v) => !v); setSaveMsg(null) }}
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border-0 transition-colors ${
              enabled ? 'bg-accent' : 'bg-neutral-300'
            }`}
            data-testid="ep-enabled-toggle"
          >
            <span
              className={`inline-block h-3.5 w-3.5 transform rounded-full bg-paper shadow-sm transition-transform ${
                enabled ? 'translate-x-[18px]' : 'translate-x-0.5'
              }`}
            />
          </button>
          <span className="text-[14px] text-ink/[0.75]">
            {enabled ? t('eventsProducer.enabledOn') : t('eventsProducer.enabledOff')}
          </span>
        </div>
        {enabled && !secretConfigured && (
          <p className="m-0 text-[14px] text-accent-2-700">
            {t('eventsProducer.enabledWarnNoSecret')}
          </p>
        )}

        <div aria-live="polite" className="empty:hidden">
          {saveMsg && (
            <p className="m-0 text-[14px] text-accent-700" data-testid="ep-save-msg">
              {saveMsg}
            </p>
          )}
          {saveError && (
            <p className="m-0 text-[14px] text-accent-2-700" data-testid="ep-save-error">
              {saveError}
            </p>
          )}
        </div>

        <div className="pt-2">
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            data-testid="ep-save-btn"
          >
            {saveMutation.isPending ? t('common.loading') : t('common.save')}
          </Button>
        </div>
      </section>

      {/* Test de connexion */}
      <section className="mt-14 max-w-[640px] space-y-3">
        <h6 className="mb-2 text-ink/[0.5]">{t('eventsProducer.testTitle')}</h6>
        <p className="m-0 text-[12px] text-ink/[0.55]">{t('eventsProducer.testHint')}</p>
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            onClick={() => testMutation.mutate()}
            disabled={!canTest || testMutation.isPending}
            data-testid="ep-test-btn"
          >
            {testMutation.isPending ? t('common.loading') : t('eventsProducer.testBtn')}
          </Button>
          {!canTest && (
            <span className="text-[12px] text-ink/[0.45]">{t('eventsProducer.testIncomplete')}</span>
          )}
        </div>
        {testResult && (
          <p
            className={`m-0 text-[14px] ${testResult.ok ? 'text-accent-700' : 'text-accent-2-700'}`}
            data-testid="ep-test-result"
          >
            {testResult.ok
              ? t('eventsProducer.testOk', { status: testResult.status })
              : t('eventsProducer.testFail', { status: testResult.status })}
          </p>
        )}
        {testError && (
          <p className="m-0 text-[14px] text-accent-2-700" data-testid="ep-test-error">
            {testError}
          </p>
        )}
      </section>

      {config && (
        <p className="mt-4 text-[12px] text-ink/[0.45]">
          {t('eventsProducer.lastUpdated', { date: new Date().toLocaleString('fr-FR') })}
        </p>
      )}

      <WiringGuide />
    </div>
  )
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-4">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-100 text-[11px] font-[700] text-accent-700">
        {n}
      </div>
      <div className="min-w-0">
        <p className="mb-1 text-[14px] font-[600] [font-family:var(--font-heading)]">{title}</p>
        <div className="text-[14px] leading-[1.6] text-ink/[0.68]">{children}</div>
      </div>
    </div>
  )
}

function Code({ children }: { children: ReactNode }) {
  return (
    <code className="rounded bg-ink/[0.06] px-1.5 py-0.5 text-[12px] text-ink/[0.85] [font-family:var(--font-mono)]">
      {children}
    </code>
  )
}

function WiringGuide() {
  const { t } = useTranslation()
  return (
    <details className="mt-14 border-t border-[var(--color-divider)]" open>
      <summary className="cursor-pointer select-none py-4 text-[15px] font-[600] [font-family:var(--font-heading)] hover:text-accent-700">
        {t('eventsProducer.guideTitle')}
      </summary>
      <div className="max-w-[80ch] space-y-6 pb-6 pt-2">
        <Step n={1} title="Créer la source inbound côté workflow">
          <p>
            Dans ag.flow workflow, créez une source d'ingestion (inbound) qui accepte les events
            docflow. Copiez son <strong>« URL d'envoi »</strong> en mode <strong>Complète</strong>{' '}
            (à coller telle quelle, ex. <Code>https://workflow.yoops.org/events/&lt;guid&gt;</Code>).
          </p>
        </Step>
        <Step n={2} title="Importer le contrat d'events (Discovery côté workflow)">
          <p>
            Côté workflow, créez une source de contrat <strong>Discovery</strong> pointant vers{' '}
            <strong>docflow</strong> (le producteur) — <em>pas</em> vers workflow :
          </p>
          <ul className="mt-2 list-inside list-disc space-y-1">
            <li>
              URL : <Code>https://doc.yoops.org/api/schemas</Code> — en{' '}
              <strong>HTTPS</strong> (un <Code>http://</Code> renvoie un 301 que la discovery ne
              suit pas).
            </li>
            <li>
              Authentification : <strong>aucune</strong>. <Code>/api/schemas</Code> est public
              (métadonnées de contrat only) — laissez <Code>auth_ref</Code> vide.
            </li>
          </ul>
          <p className="mt-2 text-[12px] text-ink/[0.5]">
            Rappel du sens : ici workflow <em>lit</em> le contrat chez docflow. L'URL de workflow,
            elle, se met dans le champ « URL d'ingestion workflow » ci-dessus (émission docflow →
            workflow).
          </p>
        </Step>
        <Step n={3} title="Créer le secret HMAC (partagé avec workflow)">
          <p>
            Chaque event est signé HMAC-SHA256 (en-tête <Code>x-signature</Code>). Dans{' '}
            <em>Clés API → onglet HMAC</em>, générez un secret, <strong>copiez sa valeur</strong> et
            renseignez-la comme secret du <strong>schéma de signature</strong> côté workflow (le
            même des deux côtés).
          </p>
        </Step>
        <Step n={4} title="Renseigner et enregistrer le formulaire">
          <ul className="list-inside list-disc space-y-1">
            <li>Collez l'« URL d'envoi » complète de l'étape 1</li>
            <li>Sélectionnez le secret HMAC de l'étape 3</li>
            <li>Cochez les eventCode à émettre (liste blanche)</li>
          </ul>
        </Step>
        <Step n={5} title="Tester puis activer">
          <p>
            Cliquez <strong>Tester la connexion</strong> (poste un event de test signé). Réponse{' '}
            <Code>HTTP 202</Code> attendue. Une fois le test vert, activez le toggle{' '}
            <strong>Émission activée</strong>.
          </p>
        </Step>
      </div>
    </details>
  )
}

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
  const [sourceId, setSourceId] = useState('')
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
      setSourceId(config.source_id ?? '')
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
        source_id: sourceId.trim() || null,
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

  if (isLoading) return <div className="p-8 text-gray-500">{t('common.loading')}</div>
  if (isError && (error as { status?: number }).status === 403) {
    return <div className="p-8 text-red-600">{t('eventsProducer.forbidden')}</div>
  }

  function toggleEvent(code: string) {
    setSaveMsg(null)
    setAllowed((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]))
  }

  const events = catalog?.events ?? []
  const canTest = Boolean(ingestionUrl.trim() && sourceId.trim() && secretConfigured)

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="mb-1 text-2xl font-semibold text-gray-900">{t('eventsProducer.title')}</h1>
      <p className="mb-6 text-sm text-gray-500">{t('eventsProducer.subtitle')}</p>

      <div className="space-y-5 rounded-lg border border-gray-200 bg-white p-6">
        {/* URL d'ingestion */}
        <Field label={t('eventsProducer.ingestionUrl')} hint={t('eventsProducer.ingestionUrlHint')}>
          <Input
            value={ingestionUrl}
            onChange={(e) => { setIngestionUrl(e.target.value); setSaveMsg(null) }}
            placeholder="https://workflow.yoops.org/ingestion"
            data-testid="ep-ingestion-url"
          />
        </Field>

        {/* source_id */}
        <Field label={t('eventsProducer.sourceId')} hint={t('eventsProducer.sourceIdHint')}>
          <Input
            value={sourceId}
            onChange={(e) => { setSourceId(e.target.value); setSaveMsg(null) }}
            placeholder="docflow-prod"
            data-testid="ep-source-id"
          />
        </Field>

        {/* source_uri */}
        <Field label={t('eventsProducer.sourceUri')} hint={t('eventsProducer.sourceUriHint')}>
          <Input
            value={sourceUri}
            onChange={(e) => { setSourceUri(e.target.value); setSaveMsg(null) }}
            placeholder="docflow"
            data-testid="ep-source-uri"
          />
        </Field>

        {/* Secret HMAC — sélection parmi les secrets gérés (onglet HMAC des Clés API) */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            {t('eventsProducer.secretRef')}
          </label>
          <select
            value={selectedSecretId}
            onChange={(e) => { setSelectedSecretId(e.target.value); setSaveMsg(null) }}
            data-testid="ep-secret-select"
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
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
          <p className={`mt-1 text-xs ${config?.secret_configured || selectedSecretId ? 'text-green-600' : 'text-amber-600'}`}>
            {config?.secret_configured || selectedSecretId
              ? t('eventsProducer.secretConfigured')
              : t('eventsProducer.secretMissing')}
          </p>
          <a href="/api-keys" className="mt-1 inline-block text-xs text-indigo-600 hover:underline">
            {t('eventsProducer.manageHmac')}
          </a>
        </div>

        {/* Events autorisés */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            {t('eventsProducer.allowedEvents')}
          </label>
          <p className="mb-2 text-xs text-gray-400">{t('eventsProducer.allowedEventsHint')}</p>
          {catalogError ? (
            <p className="text-sm text-red-600">{t('eventsProducer.catalogError')}</p>
          ) : (
            <>
              <div className="mb-2 flex gap-3 text-xs">
                <button
                  type="button"
                  className="text-indigo-600 hover:underline"
                  onClick={() => { setAllowed(events.map((e) => e.eventCode)); setSaveMsg(null) }}
                >
                  {t('eventsProducer.selectAll')}
                </button>
                <button
                  type="button"
                  className="text-indigo-600 hover:underline"
                  onClick={() => { setAllowed([]); setSaveMsg(null) }}
                >
                  {t('eventsProducer.selectNone')}
                </button>
              </div>
              <div className="space-y-1.5">
                {events.map((ev) => (
                  <label key={ev.eventCode} className="flex items-start gap-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      className="mt-0.5"
                      checked={allowed.includes(ev.eventCode)}
                      onChange={() => toggleEvent(ev.eventCode)}
                      data-testid={`ep-event-${ev.eventCode}`}
                    />
                    <span>
                      <span className="font-mono text-xs text-gray-800">{ev.eventCode}</span>
                      <span className="block text-xs text-gray-500">{ev.title}</span>
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
            role="switch"
            aria-checked={enabled}
            onClick={() => { setEnabled((v) => !v); setSaveMsg(null) }}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              enabled ? 'bg-indigo-600' : 'bg-gray-200'
            }`}
            data-testid="ep-enabled-toggle"
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                enabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
          <span className="text-sm text-gray-700">
            {enabled ? t('eventsProducer.enabledOn') : t('eventsProducer.enabledOff')}
          </span>
        </div>
        {enabled && !secretConfigured && (
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
            {t('eventsProducer.enabledWarnNoSecret')}
          </p>
        )}

        {saveMsg && (
          <p className="rounded-lg border border-green-200 bg-green-50 px-4 py-2 text-sm text-green-700"
            data-testid="ep-save-msg">
            {saveMsg}
          </p>
        )}
        {saveError && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700"
            data-testid="ep-save-error">
            {saveError}
          </p>
        )}

        <div className="pt-2">
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            data-testid="ep-save-btn"
          >
            {saveMutation.isPending ? t('common.loading') : t('common.save')}
          </Button>
        </div>
      </div>

      {/* Test de connexion */}
      <div className="mt-6 space-y-3 rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="text-sm font-semibold text-gray-800">{t('eventsProducer.testTitle')}</h2>
        <p className="text-xs text-gray-500">{t('eventsProducer.testHint')}</p>
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            onClick={() => testMutation.mutate()}
            disabled={!canTest || testMutation.isPending}
            data-testid="ep-test-btn"
          >
            {testMutation.isPending ? t('common.loading') : t('eventsProducer.testBtn')}
          </Button>
          {!canTest && <span className="text-xs text-gray-400">{t('eventsProducer.testIncomplete')}</span>}
        </div>
        {testResult && (
          <p
            className={`rounded-lg border px-4 py-2 text-sm ${
              testResult.ok
                ? 'border-green-200 bg-green-50 text-green-700'
                : 'border-red-200 bg-red-50 text-red-700'
            }`}
            data-testid="ep-test-result"
          >
            {testResult.ok
              ? t('eventsProducer.testOk', { status: testResult.status })
              : t('eventsProducer.testFail', { status: testResult.status })}
          </p>
        )}
        {testError && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700"
            data-testid="ep-test-error">
            {testError}
          </p>
        )}
      </div>

      {config && (
        <p className="mt-4 text-xs text-gray-400">
          {t('eventsProducer.lastUpdated', { date: new Date().toLocaleString('fr-FR') })}
        </p>
      )}

      <WiringGuide />
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      {children}
      <p className="mt-1 text-xs text-gray-400">{hint}</p>
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

function Code({ children }: { children: ReactNode }) {
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

function WiringGuide() {
  const { t } = useTranslation()
  return (
    <details className="mt-8 rounded-lg border border-gray-200 bg-white" open>
      <summary className="cursor-pointer select-none px-6 py-4 text-sm font-semibold text-gray-800 hover:bg-gray-50">
        {t('eventsProducer.guideTitle')}
      </summary>
      <div className="space-y-6 px-6 pb-6 pt-4">
        <Step n={1} title="Créer la source inbound côté workflow">
          <p>
            Dans ag.flow workflow, créez une source d'ingestion (inbound) qui accepte les events
            docflow. Notez son <Code>source_id</Code> et l'URL de base de l'ingestion.
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
              Authentification : <Code>/api/schemas</Code> exige un Bearer token. Créez une{' '}
              <strong>clé API docflow</strong> (page <em>Clés API</em>) et renseignez-la comme
              secret <Code>auth_ref</Code> de la source discovery.
            </li>
          </ul>
          <p className="mt-2 text-xs text-gray-400">
            Rappel du sens : ici workflow <em>lit</em> le contrat chez docflow. L'URL de workflow,
            elle, se met dans le champ « URL d'ingestion workflow » ci-dessus (émission docflow →
            workflow).
          </p>
        </Step>
        <Step n={3} title="Stocker le secret HMAC dans Harpocrate">
          <p>Chaque event est signé HMAC-SHA256 (en-tête <Code>x-signature</Code>). Le même secret est partagé avec le workflow :</p>
          <Block>{'harpocrate put docflow/workflow_hmac <secret-partagé>'}</Block>
          <p className="mt-2">Référence à saisir dans le formulaire :</p>
          <Block>{'${vault://docflow/workflow_hmac}'}</Block>
        </Step>
        <Step n={4} title="Renseigner et enregistrer le formulaire">
          <ul className="list-inside list-disc space-y-1">
            <li>URL d'ingestion + <Code>source_id</Code> de l'étape 1</li>
            <li>Référence vault du secret de l'étape 3</li>
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

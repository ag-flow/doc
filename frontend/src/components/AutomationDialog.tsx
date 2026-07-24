import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Trash2, X } from 'lucide-react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { JsonEditor, type JsonEditorHandle } from './JsonEditor'
import { contractsApi, eventsProducerApi, secretsApi, type AutomationCreate, type AutomationHeaderIn, type AutomationOut, type OperationOut } from '../lib/api'

// Variables de propriétés d'event proposées comme raccourcis (sur-ensemble des
// champs métier des events documentaires ; celles absentes rendent une chaîne vide).
const EVENT_VARS = [
  'event.code', 'event.workspaceSlug', 'event.blockSlug',
  'event.parentId', 'event.version', 'event.functionalTypeSlug',
]

interface Props {
  ws?: string
  initial?: AutomationOut | null
  onSave: (data: AutomationCreate) => void
  onClose: () => void
  saving: boolean
  error: string | null
}

interface HeaderRow {
  id: string
  name: string
  value: string
  secretRef: string
  valuePrefix: string
  isSecret: boolean
  required: boolean
  enabled: boolean
}

function newRow(): HeaderRow {
  return { id: crypto.randomUUID(), name: '', value: '', secretRef: '', valuePrefix: '', isSecret: false, required: false, enabled: true }
}

export function AutomationDialog({ initial, onSave, onClose, saving, error }: Props) {
  const jsonRef = useRef<JsonEditorHandle>(null)

  // Fermeture par la touche Échap.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const [label, setLabel] = useState(initial?.label ?? '')
  const [active, setActive] = useState(initial?.active ?? true)
  const [eventCodes, setEventCodes] = useState<string[]>(initial?.event_codes ?? [])
  const [delay, setDelay] = useState(String(initial?.delay_minutes ?? 0))
  const [url, setUrl] = useState(initial?.url ?? '')
  const [method, setMethod] = useState(initial?.http_method ?? 'POST')
  const [contractId, setContractId] = useState(initial?.contract_ref ?? '')
  const [operationId, setOperationId] = useState(initial?.operation_id ?? '')
  const [headers, setHeaders] = useState<HeaderRow[]>(
    initial?.headers.map((h) => ({
      id: h.id,
      name: h.name,
      value: h.value ?? '',
      secretRef: h.secret_ref ?? '',
      valuePrefix: h.value_prefix ?? '',
      // Un header d'auth (préfixe posé, pas encore de secret) reste en mode secret.
      isSecret: h.secret_ref != null || (h.value == null && !!h.value_prefix),
      required: h.required,
      enabled: h.enabled,
    })) ?? []
  )

  const { data: contracts = [] } = useQuery({
    queryKey: ['contracts'],
    queryFn: () => contractsApi.list(),
    staleTime: 60_000,
  })

  const { data: contractDetail } = useQuery({
    queryKey: ['contract-detail', contractId],
    queryFn: () => contractsApi.detail(contractId),
    enabled: !!contractId,
    staleTime: 60_000,
  })

  // Catalogue public des eventCodes (source unique des types déclencheurs).
  const { data: catalog } = useQuery({
    queryKey: ['events-catalog'],
    queryFn: () => eventsProducerApi.catalog(),
    staleTime: 300_000,
  })
  const eventTypes = catalog?.events ?? []

  // Secrets (Mes secrets) proposés en liste de sélection pour les headers d'auth.
  const { data: secrets = [] } = useQuery({
    queryKey: ['user-secrets'],
    queryFn: () => secretsApi.list(),
    staleTime: 60_000,
  })

  const operations = contractDetail?.operations ?? []

  function toggleEvent(code: string) {
    setEventCodes((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]))
  }

  const [copiedVar, setCopiedVar] = useState<string | null>(null)
  async function copyVariable(v: string) {
    try {
      await navigator.clipboard?.writeText(`{${v}}`)
      setCopiedVar(v)
      setTimeout(() => setCopiedVar(null), 1200)
    } catch {
      /* presse-papier indisponible : on ignore */
    }
  }

  // Ajoute les headers d'auth requis par la sécurité de l'opération (mode
  // secret + préfixe, ex. « Bearer »). Idempotent : ne double pas un header
  // déjà présent (par nom).
  function addAuthHeadersFor(op: OperationOut) {
    if (!op.auth_headers?.length) return
    setHeaders((prev) => {
      const names = new Set(prev.map((h) => h.name.toLowerCase()))
      const add: HeaderRow[] = op.auth_headers
        .filter((a) => !names.has(a.header.toLowerCase()))
        .map((a) => ({
          id: crypto.randomUUID(),
          name: a.header,
          value: '',
          secretRef: '',
          valuePrefix: a.value_prefix,
          isSecret: true,
          required: true,
          enabled: true,
        }))
      return add.length ? [...prev, ...add] : prev
    })
  }

  // À l'ouverture (ou quand le catalogue d'opérations se charge), ajoute les
  // headers d'auth de l'opération déjà sélectionnée — sans toucher au body.
  useEffect(() => {
    const op = operations.find((o) => o.operation_id === operationId)
    if (op) addAuthHeadersFor(op)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operations, operationId])

  function selectOperation(opId: string) {
    setOperationId(opId)
    const op = operations.find((o) => o.operation_id === opId)
    if (!op) return
    setMethod(op.method)
    if (op.body_skeleton) {
      jsonRef.current?.setValue(JSON.stringify(op.body_skeleton, null, 2))
    }
    // Si le contrat déclare un serveur, construire l'URL d'appel : server + path.
    const server = contractDetail?.servers?.[0]
    if (server) {
      const base = server.replace(/\/+$/, '')
      const path = op.path.startsWith('/') ? op.path : `/${op.path}`
      setUrl(`${base}${path}`)
    }
    addAuthHeadersFor(op)
  }

  function submit() {
    const bodyTemplate = jsonRef.current?.getValue()?.trim() || null
    const hdrs: AutomationHeaderIn[] = headers
      .filter((h) => h.name.trim())
      .map((h) => ({
        name: h.name.trim(),
        value: h.isSecret ? null : h.value || null,
        secret_ref: h.isSecret ? h.secretRef || null : null,
        value_prefix: h.valuePrefix || null,
        required: h.required,
        enabled: h.enabled,
      }))
    onSave({
      label, active, event_codes: eventCodes,
      delay_minutes: parseInt(delay) || 0,
      contract_ref: contractId || null,
      operation_id: operationId || null,
      url, http_method: method, body_template: bodyTemplate, headers: hdrs,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 overflow-y-auto"
      onClick={onClose}>
      <div className="w-full max-w-2xl rounded-lg bg-white p-6 shadow-xl space-y-4 my-4"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">{initial ? 'Modifier' : 'Nouvel automate'}</h2>
          <button type="button" onClick={onClose} title="Fermer" aria-label="Fermer"
            className="rounded p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
            data-testid="auto-dialog-close">
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="block text-sm font-medium mb-1">Libellé</label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="active" checked={active} onChange={(e) => setActive(e.target.checked)} />
            <label htmlFor="active" className="text-sm">Actif</label>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Délai débounce (minutes)</label>
            <Input type="number" min={0} value={delay} onChange={(e) => setDelay(e.target.value)} className="w-24" />
          </div>
          <div className="col-span-2">
            <label className="block text-sm font-medium mb-1">Events déclencheurs</label>
            <div className="grid grid-cols-2 gap-1.5 rounded border border-gray-200 p-2">
              {eventTypes.map((ev) => (
                <label key={ev.eventCode} className="flex items-start gap-1.5 text-sm" data-testid={`auto-event-${ev.eventCode}`}>
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={eventCodes.includes(ev.eventCode)}
                    onChange={() => toggleEvent(ev.eventCode)}
                  />
                  <span>
                    {ev.title}
                    <span className="block font-mono text-[10px] text-gray-400">{ev.eventCode}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium mb-1">Contrat OpenAPI</label>
            <select className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={contractId} onChange={(e) => { setContractId(e.target.value); setOperationId('') }}
              data-testid="auto-contract-select">
              <option value="">— aucun —</option>
              {contracts.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Opération</label>
            <select className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={operationId} onChange={(e) => selectOperation(e.target.value)} disabled={!contractId}
              data-testid="auto-operation-select">
              <option value="">— sélectionner —</option>
              {operations.map((op) => (
                <option key={op.operation_id ?? op.path} value={op.operation_id ?? ''}>
                  {op.method} {op.path}{op.summary ? ` — ${op.summary}` : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="col-span-2">
            <label className="block text-sm font-medium mb-1">URL</label>
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" data-testid="auto-url" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Méthode</label>
            <select className="rounded border border-gray-300 px-3 py-2 text-sm"
              value={method} onChange={(e) => setMethod(e.target.value)}>
              {['GET','POST','PUT','PATCH','DELETE'].map((m) => <option key={m}>{m}</option>)}
            </select>
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm font-medium">Corps (JSON)</label>
            <div className="flex flex-wrap gap-1 justify-end">
              {['id_document', 'title', 'content', 'doc_url', ...EVENT_VARS].map((v) => (
                <button key={v} type="button" onClick={() => copyVariable(v)}
                  title="Copier dans le presse-papier"
                  className={`rounded px-2 py-0.5 text-xs font-mono transition-colors ${
                    copiedVar === v ? 'bg-green-100 text-green-700' : 'bg-gray-100 hover:bg-gray-200'
                  }`}>
                  {copiedVar === v ? '✓ copié' : `{${v}}`}
                </button>
              ))}
            </div>
          </div>
          <JsonEditor ref={jsonRef} initialValue={initial?.body_template ?? ''} />
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">Headers</label>
            <button type="button" onClick={() => setHeaders((h) => [...h, newRow()])}
              className="flex items-center gap-1 text-xs text-indigo-600 hover:underline">
              <Plus size={12} /> Ajouter
            </button>
          </div>
          {headers.map((h, i) => (
            <div key={h.id} className="mb-2 flex items-center gap-2">
              <Input value={h.name} onChange={(e) => setHeaders((arr) => arr.map((r, j) => j===i ? {...r, name:e.target.value} : r))}
                placeholder="Nom" className="w-36" data-testid={`header-name-${i}`} />
              <Input value={h.valuePrefix}
                onChange={(e) => setHeaders((arr) => arr.map((r, j) => j===i ? {...r, valuePrefix:e.target.value} : r))}
                placeholder="préfixe" title="Préfixe de valeur (ex. « Bearer »)"
                className="w-24 font-mono text-xs" />
              <label className="flex items-center gap-1 text-xs whitespace-nowrap">
                <input type="checkbox" checked={h.isSecret}
                  onChange={(e) => setHeaders((arr) => arr.map((r, j) => j===i ? {...r, isSecret:e.target.checked} : r))} />
                Secret
              </label>
              {h.isSecret ? (
                <select value={h.secretRef}
                  onChange={(e) => setHeaders((arr) => arr.map((r, j) => j===i ? {...r, secretRef:e.target.value} : r))}
                  className="flex-1 rounded border border-gray-300 px-2 py-2 text-xs"
                  data-testid={`header-secret-${i}`}>
                  <option value="">— choisir un secret —</option>
                  {secrets.map((s) => <option key={s.id} value={`\${secret://${s.id}}`}>{s.label}</option>)}
                  {h.secretRef && !secrets.some((s) => `\${secret://${s.id}}` === h.secretRef) && (
                    <option value={h.secretRef}>{h.secretRef} (existant)</option>
                  )}
                </select>
              ) : (
                <Input value={h.value}
                  onChange={(e) => setHeaders((arr) => arr.map((r, j) => j===i ? {...r, value:e.target.value} : r))}
                  placeholder="Valeur" className="flex-1" />
              )}
              <button type="button" onClick={() => setHeaders((arr) => arr.filter((_, j) => j !== i))}
                className="text-gray-400 hover:text-red-500"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>

        {error && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700"
            data-testid="auto-dialog-error">
            Échec de l'enregistrement : {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={saving}>Annuler</Button>
          <Button onClick={submit} disabled={saving || !label.trim() || !url.trim()}>
            {saving ? 'Enregistrement…' : 'Enregistrer'}
          </Button>
        </div>
      </div>
    </div>
  )
}

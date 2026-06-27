import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { JsonEditor, type JsonEditorHandle } from './JsonEditor'
import { contractsApi, type AutomationCreate, type AutomationHeaderIn, type AutomationOut } from '../lib/api'

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
  isSecret: boolean
  required: boolean
  enabled: boolean
}

function newRow(): HeaderRow {
  return { id: crypto.randomUUID(), name: '', value: '', secretRef: '', isSecret: false, required: false, enabled: true }
}

export function AutomationDialog({ initial, onSave, onClose, saving, error }: Props) {
  const jsonRef = useRef<JsonEditorHandle>(null)

  const [label, setLabel] = useState(initial?.label ?? '')
  const [active, setActive] = useState(initial?.active ?? true)
  const [onCreate, setOnCreate] = useState(initial?.on_create ?? false)
  const [onUpdate, setOnUpdate] = useState(initial?.on_update ?? false)
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
      isSecret: h.secret_ref != null,
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

  const operations = contractDetail?.operations ?? []

  function insertVariable(v: string) {
    const cur = jsonRef.current?.getValue() ?? ''
    jsonRef.current?.setValue(cur + `{${v}}`)
  }

  function selectOperation(opId: string) {
    setOperationId(opId)
    const op = operations.find((o) => o.operation_id === opId)
    if (!op) return
    setMethod(op.method)
    if (op.body_skeleton) {
      jsonRef.current?.setValue(JSON.stringify(op.body_skeleton, null, 2))
    }
  }

  function submit() {
    const bodyTemplate = jsonRef.current?.getValue()?.trim() || null
    const hdrs: AutomationHeaderIn[] = headers
      .filter((h) => h.name.trim())
      .map((h) => ({
        name: h.name.trim(),
        value: h.isSecret ? null : h.value || null,
        secret_ref: h.isSecret ? h.secretRef || null : null,
        required: h.required,
        enabled: h.enabled,
      }))
    onSave({
      label, active, on_create: onCreate, on_update: onUpdate,
      delay_minutes: parseInt(delay) || 0,
      contract_ref: contractId || null,
      operation_id: operationId || null,
      url, http_method: method, body_template: bodyTemplate, headers: hdrs,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 overflow-y-auto">
      <div className="w-full max-w-2xl rounded-lg bg-white p-6 shadow-xl space-y-4 my-4">
        <h2 className="text-lg font-bold">{initial ? 'Modifier' : 'Nouvel automate'}</h2>

        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="block text-sm font-medium mb-1">Libellé</label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="active" checked={active} onChange={(e) => setActive(e.target.checked)} />
            <label htmlFor="active" className="text-sm">Actif</label>
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={onCreate} onChange={(e) => setOnCreate(e.target.checked)} />
              À la création
            </label>
            <label className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={onUpdate} onChange={(e) => setOnUpdate(e.target.checked)} />
              À la modification
            </label>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Délai débounce (minutes)</label>
            <Input type="number" min={0} value={delay} onChange={(e) => setDelay(e.target.value)} className="w-24" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium mb-1">Contrat OpenAPI</label>
            <select className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={contractId} onChange={(e) => { setContractId(e.target.value); setOperationId('') }}>
              <option value="">— aucun —</option>
              {contracts.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Opération</label>
            <select className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              value={operationId} onChange={(e) => selectOperation(e.target.value)} disabled={!contractId}>
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
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
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
            <div className="flex gap-1">
              {['{id_document}','{title}','{content}'].map((v) => (
                <button key={v} type="button" onClick={() => insertVariable(v.slice(1,-1))}
                  className="rounded bg-gray-100 px-2 py-0.5 text-xs font-mono hover:bg-gray-200">
                  {v}
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
                placeholder="Nom" className="w-40" />
              <label className="flex items-center gap-1 text-xs whitespace-nowrap">
                <input type="checkbox" checked={h.isSecret}
                  onChange={(e) => setHeaders((arr) => arr.map((r, j) => j===i ? {...r, isSecret:e.target.checked} : r))} />
                Secret
              </label>
              {h.isSecret
                ? <Input value={h.secretRef}
                    onChange={(e) => setHeaders((arr) => arr.map((r, j) => j===i ? {...r, secretRef:e.target.value} : r))}
                    placeholder="${vault://wallet:/chemin}" className="flex-1 font-mono text-xs" />
                : <Input value={h.value}
                    onChange={(e) => setHeaders((arr) => arr.map((r, j) => j===i ? {...r, value:e.target.value} : r))}
                    placeholder="Valeur" className="flex-1" />
              }
              <button type="button" onClick={() => setHeaders((arr) => arr.filter((_, j) => j !== i))}
                className="text-gray-400 hover:text-red-500"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

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

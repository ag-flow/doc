import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CaretRight, Plus, Trash, X } from '@phosphor-icons/react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { JsonEditor, type JsonEditorHandle } from './JsonEditor'
import {
  api, contractsApi, docsApi, eventsProducerApi, secretsApi,
  type AutomationCreate, type AutomationHeaderIn, type AutomationOut,
  type DataBlockOut, type FunctionalType, type OperationOut, type WorkspaceOut,
} from '../lib/api'

// Variables de propriétés d'event proposées comme raccourcis (sur-ensemble des
// champs métier des events documentaires ; celles absentes rendent une chaîne vide).
const EVENT_VARS = [
  'event.code', 'event.workspaceSlug', 'event.blockSlug',
  'event.parentId', 'event.version', 'event.functionalTypeSlug',
]

type Tab = 'label' | 'events' | 'call'

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

/** Blocs d'un workspace couvert (arbre de couverture) : cases de filtre + type. */
function WorkspaceBlocksNode({
  wsSlug, blockSlugs, onToggleBlock,
}: {
  wsSlug: string
  blockSlugs: string[]
  onToggleBlock: (slug: string) => void
}) {
  const { data: blocks = [], isLoading } = useQuery<DataBlockOut[]>({
    queryKey: ['blocs', wsSlug],
    queryFn: () => docsApi.getBlocks(wsSlug),
    staleTime: 60_000,
  })
  if (isLoading) return <p className="text-muted ml-6 text-[12px]">Chargement des blocs…</p>
  if (blocks.length === 0) return <p className="text-muted ml-6 text-[12px]">Aucun bloc</p>
  return (
    <div className="ml-6 space-y-0.5 border-l border-[var(--color-divider)] pl-3">
      {blocks.map((b) => (
        <label key={b.slug} className="flex items-center gap-1.5 text-sm" data-testid={`auto-block-${wsSlug}-${b.slug}`}>
          <input type="checkbox" checked={blockSlugs.includes(b.slug)}
            onChange={() => onToggleBlock(b.slug)} />
          <span className="truncate">{b.label}</span>
          <span className="tag tag-neutral ml-auto shrink-0 text-[10px]">
            {b.functional_type_slug}
          </span>
        </label>
      ))}
    </div>
  )
}

/** Section repliable de l'onglet Events. Repliée, elle tient sur une ligne
 *  avec son résumé ; dépliée, son corps défile dans une hauteur bornée au lieu
 *  de pousser le reste de l'onglet. */
function Section({ title, hint, summary, defaultOpen = true, maxBody = false, children }: {
  title: string
  hint?: string
  /** Résumé affiché quand la section est repliée (« 2 workspaces · 3 blocs »). */
  summary?: string
  defaultOpen?: boolean
  /** Borne la hauteur du corps (~200px) avec défilement interne. */
  maxBody?: boolean
  children: React.ReactNode
}) {
  return (
    <details open={defaultOpen} className="group rounded-md border border-[var(--color-divider)]">
      <summary className="flex cursor-pointer select-none items-center gap-2 px-3 py-2 text-[14px] font-[600] [font-family:var(--font-heading)] hover:bg-ink/[0.04] [&::-webkit-details-marker]:hidden">
        <CaretRight size={13} weight="duotone" className="shrink-0 text-ink/[0.4] transition-transform group-open:rotate-90" />
        {title}
        {summary && (
          <span className="font-normal text-[12px] text-accent-700 [font-family:var(--font-body)] group-open:hidden">
            {summary}
          </span>
        )}
        {hint && <span className="font-normal text-[11px] text-ink/[0.45] [font-family:var(--font-body)]">{hint}</span>}
      </summary>
      <div className={`border-t border-[var(--color-divider)] p-2.5 ${maxBody ? 'dialog-scroll max-h-[200px] overflow-y-auto' : ''}`}>
        {children}
      </div>
    </details>
  )
}

export function AutomationDialog({ ws, initial, onSave, onClose, saving, error }: Props) {
  const jsonRef = useRef<JsonEditorHandle>(null)
  const [tab, setTab] = useState<Tab>('label')

  // Le focus revient à l'élément qui a ouvert la modale (le bouton de la ligne) :
  // capturé au montage, restauré au démontage — Échap comme Annuler.
  const openerRef = useRef<HTMLElement | null>(null)
  useEffect(() => {
    openerRef.current = document.activeElement as HTMLElement | null
    return () => openerRef.current?.focus()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const [label, setLabel] = useState(initial?.label ?? '')
  // Portée : workspaces couverts. Défaut à la création = le workspace courant.
  const [workspaceSlugs, setWorkspaceSlugs] = useState<string[]>(
    initial?.workspace_slugs?.length ? initial.workspace_slugs : ws ? [ws] : [],
  )
  const [eventCodes, setEventCodes] = useState<string[]>(initial?.event_codes ?? [])
  const [stopChain, setStopChain] = useState(initial?.stop_chain ?? false)
  const [blockSlugs, setBlockSlugs] = useState<string[]>(initial?.block_slugs ?? [])
  const [typeSlugs, setTypeSlugs] = useState<string[]>(initial?.functional_type_slugs ?? [])
  const [delay, setDelay] = useState(String(initial?.delay_minutes ?? 0))
  const [url, setUrl] = useState(initial?.url ?? '')
  const [method, setMethod] = useState(initial?.http_method ?? 'POST')
  const [contractId, setContractId] = useState(initial?.contract_ref ?? '')
  const [operationId, setOperationId] = useState(initial?.operation_id ?? '')
  // Le template vit dans du state (pas seulement dans CodeMirror) : l'onglet
  // Appel est démonté quand un autre onglet est actif, et un submit depuis un
  // autre onglet effacerait sinon le template en base (body_template: null).
  const [bodyTemplate, setBodyTemplate] = useState(initial?.body_template ?? '')
  const [headers, setHeaders] = useState<HeaderRow[]>(
    initial?.headers.map((h) => ({
      id: h.id,
      name: h.name,
      value: h.value ?? '',
      secretRef: h.secret_ref ?? '',
      valuePrefix: h.value_prefix ?? '',
      isSecret: h.secret_ref != null || (h.value == null && !!h.value_prefix),
      required: h.required,
      enabled: h.enabled,
    })) ?? []
  )

  const { data: contracts = [] } = useQuery({
    queryKey: ['contracts'], queryFn: () => contractsApi.list(), staleTime: 60_000,
  })
  const { data: contractDetail } = useQuery({
    queryKey: ['contract-detail', contractId],
    queryFn: () => contractsApi.detail(contractId),
    enabled: !!contractId, staleTime: 60_000,
  })
  const { data: catalog } = useQuery({
    queryKey: ['events-catalog'], queryFn: () => eventsProducerApi.catalog(), staleTime: 300_000,
  })
  const eventTypes = catalog?.events ?? []
  const { data: secrets = [] } = useQuery({
    queryKey: ['user-secrets'], queryFn: () => secretsApi.list(), staleTime: 60_000,
  })
  // Tous les workspaces (pour la portée multi-workspaces).
  const { data: workspaces = [] } = useQuery<WorkspaceOut[]>({
    queryKey: ['workspaces'], queryFn: () => api.get<WorkspaceOut[]>('/workspaces'), staleTime: 60_000,
  })
  // Types du workspace (filtre type de document). Les blocs sont chargés par
  // workspace couvert, dans l'arbre de couverture (WorkspaceBlocksNode).
  const { data: types = [] } = useQuery<FunctionalType[]>({
    queryKey: ['types', ws], queryFn: () => api.get<FunctionalType[]>(`/workspaces/${ws}/types`),
    enabled: !!ws, staleTime: 60_000,
  })

  const operations = contractDetail?.operations ?? []

  const toggle = (arr: string[], v: string) => arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]

  const [copiedVar, setCopiedVar] = useState<string | null>(null)
  async function copyVariable(v: string) {
    try {
      await navigator.clipboard?.writeText(`{${v}}`)
      setCopiedVar(v)
      setTimeout(() => setCopiedVar(null), 1200)
    } catch { /* presse-papier indisponible */ }
  }

  function addAuthHeadersFor(op: OperationOut) {
    if (!op.auth_headers?.length) return
    setHeaders((prev) => {
      const names = new Set(prev.map((h) => h.name.toLowerCase()))
      const add: HeaderRow[] = op.auth_headers
        .filter((a) => !names.has(a.header.toLowerCase()))
        .map((a) => ({
          id: crypto.randomUUID(), name: a.header, value: '', secretRef: '',
          valuePrefix: a.value_prefix, isSecret: true, required: true, enabled: true,
        }))
      return add.length ? [...prev, ...add] : prev
    })
  }

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
    if (op.body_skeleton) jsonRef.current?.setValue(JSON.stringify(op.body_skeleton, null, 2))
    const server = contractDetail?.servers?.[0]
    if (server) {
      const base = server.replace(/\/+$/, '')
      const path = op.path.startsWith('/') ? op.path : `/${op.path}`
      setUrl(`${base}${path}`)
    }
    addAuthHeadersFor(op)
  }

  function submit() {
    // L'éditeur monté fait foi (édition en cours) ; sinon le state suffit.
    const raw = jsonRef.current?.getValue() ?? bodyTemplate
    const body = raw.trim() || null
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
    // Pas de `active` : la règle est créée désactivée ; l'activation se fait via
    // le toggle de la carte (préservé à l'édition).
    onSave({
      label, event_codes: eventCodes,
      workspace_slugs: workspaceSlugs,
      block_slugs: blockSlugs, functional_type_slugs: typeSlugs,
      stop_chain: stopChain,
      delay_minutes: parseInt(delay) || 0,
      contract_ref: contractId || null,
      operation_id: operationId || null,
      url, http_method: method, body_template: body, headers: hdrs,
    })
  }

  const TabBtn = ({ id, children }: { id: Tab; children: React.ReactNode }) => (
    <button type="button" onClick={() => setTab(id)}
      className={`border-0 border-b-2 bg-transparent px-4 py-2 text-[14px] font-[600] [font-family:var(--font-heading)] transition-colors ${
        tab === id
          ? 'border-b-accent text-accent-700 [border-bottom-style:solid]'
          : 'border-b-transparent text-ink/[0.55] hover:text-ink [border-bottom-style:solid]'
      }`} data-testid={`auto-tab-${id}`}>
      {children}
    </button>
  )

  return (
    <div className="dialog-backdrop z-50 overflow-y-auto" onClick={onClose}>
      {/* Taille FIXE (celle du plus grand onglet, « Appel ») : changer d'onglet
          ne fait pas sauter la fenêtre ; seul le corps défile, les onglets et
          les actions restent visibles (DoD). */}
      <div className="dialog my-4 h-[min(94vh,980px)] w-full !max-w-4xl"
        role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h4 className="dialog-title m-0">{initial ? 'Modifier' : 'Nouvel automate'}</h4>
          <button type="button" onClick={onClose} title="Fermer" aria-label="Fermer"
            className="border-0 bg-transparent p-1 text-ink/[0.4] transition-colors hover:text-ink"
            data-testid="auto-dialog-close">
            <X size={18} weight="bold" />
          </button>
        </div>

        <div className="flex gap-1 border-b border-[var(--color-divider)]">
          <TabBtn id="label">Libellé</TabBtn>
          <TabBtn id="events">Events déclencheurs</TabBtn>
          <TabBtn id="call">Appel</TabBtn>
        </div>

        <div className="dialog-scroll min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-2">
        {/* ── Onglet Libellé ── */}
        {tab === 'label' && (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-[12px] text-ink/[0.7]">Libellé</label>
              <Input value={label} onChange={(e) => setLabel(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-[12px] text-ink/[0.7]">Délai débounce (minutes)</label>
              <Input type="number" min={0} value={delay} onChange={(e) => setDelay(e.target.value)} className="w-32" />
            </div>
            <p className="text-[12px] text-ink/[0.5]">
              La règle est créée <strong>désactivée</strong> ; activez-la ensuite via le toggle de la carte.
            </p>
          </div>
        )}

        {/* ── Onglet Events déclencheurs + filtres ── */}
        {tab === 'events' && (
          <div className="space-y-4">
            <Section
              title="Couverture de déclenchement"
              defaultOpen={false}
              maxBody
              summary={`${workspaceSlugs.length} workspace${workspaceSlugs.length > 1 ? 's' : ''} · ${
                blockSlugs.length > 0 ? `${blockSlugs.length} bloc${blockSlugs.length > 1 ? 's' : ''}` : 'tous les blocs'
              }`}
              hint="au moins un workspace ; blocs cochés = filtre, aucun = tous">
              <div className="space-y-1.5">
                {workspaces.map((w) => {
                  const covered = workspaceSlugs.includes(w.slug)
                  return (
                    <div key={w.slug}>
                      <label className="flex items-center gap-1.5 text-sm font-medium" data-testid={`auto-ws-${w.slug}`}>
                        <input type="checkbox" checked={covered}
                          onChange={() => setWorkspaceSlugs((p) => toggle(p, w.slug))} />
                        <span className="truncate">{w.label}</span>
                        <span className="shrink-0 text-[10px] text-accent-700 [font-family:var(--font-mono)]">{w.slug}</span>
                      </label>
                      {covered && (
                        <WorkspaceBlocksNode
                          wsSlug={w.slug}
                          blockSlugs={blockSlugs}
                          onToggleBlock={(slug) => setBlockSlugs((p) => toggle(p, slug))}
                        />
                      )}
                    </div>
                  )
                })}
              </div>
            </Section>

            {workspaceSlugs.length === 0 && (
              <p className="field-error m-0" data-testid="auto-ws-empty" role="alert">
                Un automate doit couvrir au moins un workspace.
              </p>
            )}

            <Section title="Events déclencheurs">
              <div className="grid grid-cols-2 gap-1.5">
                {eventTypes.map((ev) => (
                  <label key={ev.eventCode} className="flex items-start gap-1.5 text-sm" data-testid={`auto-event-${ev.eventCode}`}>
                    <input type="checkbox" className="mt-0.5"
                      checked={eventCodes.includes(ev.eventCode)}
                      onChange={() => setEventCodes((p) => toggle(p, ev.eventCode))} />
                    <span>{ev.title}
                      <span className="block text-[10px] text-accent-700 [font-family:var(--font-mono)]">{ev.eventCode}</span>
                    </span>
                  </label>
                ))}
              </div>
            </Section>

            <Section title="Filtre type de document" hint="combiné en ET — vide = tous">
              <div className="grid grid-cols-2 gap-1">
                {types.length === 0 && <p className="text-[12px] text-ink/[0.5]">Aucun type</p>}
                {types.map((t) => (
                  <label key={t.slug} className="flex items-center gap-1.5 text-sm" data-testid={`auto-type-${t.slug}`}>
                    <input type="checkbox" checked={typeSlugs.includes(t.slug)}
                      onChange={() => setTypeSlugs((p) => toggle(p, t.slug))} />
                    <span className="truncate">{t.label}</span>
                  </label>
                ))}
              </div>
            </Section>

            <label className="flex items-start gap-2 text-[14px]" data-testid="auto-stop-chain">
              <input type="checkbox" className="mt-0.5" checked={stopChain}
                onChange={(e) => setStopChain(e.target.checked)} />
              <span>
                Stopper la chaîne si déclenché
                <span className="block text-[12px] text-ink/[0.55]">
                  Si cet automate matche l'event ET que l'appel réussit, les automates de
                  priorité inférieure ne traitent pas cet event.
                </span>
              </span>
            </label>
          </div>
        )}

        {/* ── Onglet Appel ── */}
        {tab === 'call' && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-[12px] text-ink/[0.7]">Contrat OpenAPI</label>
                <select className="input"
                  value={contractId} onChange={(e) => { setContractId(e.target.value); setOperationId('') }}
                  data-testid="auto-contract-select">
                  <option value="">— aucun —</option>
                  {contracts.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[12px] text-ink/[0.7]">Opération</label>
                <select className="input"
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
                <label className="mb-1 block text-[12px] text-ink/[0.7]">URL</label>
                <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" data-testid="auto-url" />
              </div>
              <div>
                <label className="mb-1 block text-[12px] text-ink/[0.7]">Méthode</label>
                <select className="input w-auto"
                  value={method} onChange={(e) => setMethod(e.target.value)}>
                  {['GET','POST','PUT','PATCH','DELETE'].map((m) => <option key={m}>{m}</option>)}
                </select>
              </div>
            </div>

            <div>
              <div className="mb-1 flex items-center justify-between">
                <label className="text-sm font-medium">Corps (JSON)</label>
                <div className="flex flex-wrap justify-end gap-1">
                  {['id_document', 'title', 'content', 'doc_type', 'doc_url', ...EVENT_VARS].map((v) => (
                    <button key={v} type="button" onClick={() => copyVariable(v)}
                      title="Copier dans le presse-papier"
                      className={`rounded px-2 py-0.5 font-mono text-xs transition-colors ${
                        copiedVar === v ? 'bg-accent-100 text-accent-800' : 'bg-surface hover:bg-neutral-300/60'
                      }`}>
                      {copiedVar === v ? '✓ copié' : `{${v}}`}
                    </button>
                  ))}
                </div>
              </div>
              <JsonEditor ref={jsonRef} initialValue={bodyTemplate} onChange={setBodyTemplate} />
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-sm font-medium">Headers</label>
                <button type="button" onClick={() => setHeaders((h) => [...h, newRow()])}
                  className="flex items-center gap-1 border-0 bg-transparent p-0 text-[12px] text-accent-700 hover:underline">
                  <Plus size={12} weight="duotone" /> Ajouter
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
                  <label className="flex items-center gap-1 whitespace-nowrap text-xs">
                    <input type="checkbox" checked={h.isSecret}
                      onChange={(e) => setHeaders((arr) => arr.map((r, j) => j===i ? {...r, isSecret:e.target.checked} : r))} />
                    Secret
                  </label>
                  {h.isSecret ? (
                    <select value={h.secretRef}
                      onChange={(e) => setHeaders((arr) => arr.map((r, j) => j===i ? {...r, secretRef:e.target.value} : r))}
                      className="input flex-1 text-[12px]"
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
                    className="border-0 bg-transparent p-0 text-ink/[0.4] hover:text-accent-2-700"><Trash size={14} weight="duotone" /></button>
                </div>
              ))}
            </div>
          </div>
        )}
        </div>

        <div aria-live="polite" className="empty:hidden">
          {error && (
            <p className="field-error m-0" data-testid="auto-dialog-error">
              Échec de l'enregistrement : {error}
            </p>
          )}
        </div>

        <div className="dialog-actions m-0 border-t border-[var(--color-divider)] pt-3">
          <Button variant="secondary" onClick={onClose} disabled={saving}>Annuler</Button>
          <Button onClick={submit} disabled={saving || !label.trim() || !url.trim() || workspaceSlugs.length === 0}>
            {saving ? 'Enregistrement…' : 'Enregistrer'}
          </Button>
        </div>
      </div>
    </div>
  )
}

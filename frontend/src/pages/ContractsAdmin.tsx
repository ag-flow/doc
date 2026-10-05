import { lazy, Suspense, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowClockwise, Eye, Plus, Trash, X } from '@phosphor-icons/react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'
import { SectionHead } from '../components/SectionHead'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, TableSkeleton } from '../components/ui/states'
import { useToast } from '../components/Toast'
import { relativeDate } from '../lib/relativeDate'
import { contractsApi, type ContractDetailOut, type ContractOut } from '../lib/api'

// Swagger UI est lourd : chargé en lazy, uniquement à l'ouverture de la visu.
const SwaggerViewer = lazy(() => import('../components/SwaggerViewer'))

/** Verbe HTTP en tag : GET neutre, POST/PUT/PATCH cyan, DELETE magenta. */
function MethodTag({ method }: { method: string }) {
  const m = method.toUpperCase()
  const variant = m === 'DELETE' ? 'tag-accent-2' : m === 'GET' ? 'tag-neutral' : 'tag-accent'
  return <span className={`tag ${variant} w-14 justify-center text-[10px]`}>{m}</span>
}

// ── Import contrat ────────────────────────────────────────────────────────────

function ContractImportForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient()
  const [label, setLabel] = useState('')
  const [url, setUrl] = useState('')
  const [jsonText, setJsonText] = useState('')
  const [error, setError] = useState<string | null>(null)

  const importMut = useMutation({
    mutationFn: (body: Parameters<typeof contractsApi.import>[0]) => contractsApi.import(body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['contracts'] }); onDone() },
    // DoD : l'erreur de parsing s'affiche sous le formulaire — les champs
    // gardent leur contenu, l'utilisateur corrige au lieu de tout retaper.
    onError: (e: Error) => setError(e.message),
  })

  function submit() {
    setError(null)
    if (!label.trim()) return setError('Libellé requis')
    if (url.trim()) {
      importMut.mutate({ label: label.trim(), source_url: url.trim(), raw_spec: {} })
    } else {
      try {
        const raw_spec = JSON.parse(jsonText) as object
        importMut.mutate({ label: label.trim(), raw_spec })
      } catch {
        setError('JSON invalide')
      }
    }
  }

  return (
    <form
      className="mt-6 flex flex-col gap-3 border-t border-[var(--color-divider)] pt-4"
      onSubmit={(e) => { e.preventDefault(); submit() }}
      data-testid="contract-import-form"
    >
      <Field label="Libellé" htmlFor="contract-label">
        <Input id="contract-label" value={label} onChange={(e) => setLabel(e.target.value)}
          placeholder="ag-flow.rag" data-testid="contract-label" />
      </Field>
      <Field label="URL source" htmlFor="contract-url"
        hint="ou collez le contrat JSON ci-dessous">
        <Input id="contract-url" value={url} onChange={(e) => setUrl(e.target.value)}
          placeholder="https://…/openapi.json" data-testid="contract-url" />
      </Field>
      {!url.trim() && (
        <textarea
          value={jsonText}
          onChange={(e) => setJsonText(e.target.value)}
          className="input h-28 resize-y text-[12px] [font-family:var(--font-mono)]"
          placeholder="Coller ici le contrat OpenAPI en JSON…"
          data-testid="contract-json"
        />
      )}
      <div aria-live="polite" className="empty:hidden">
        {error && <p className="field-error m-0" data-testid="contract-import-error">{error}</p>}
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={importMut.isPending}
          data-testid="contract-import-submit">
          {importMut.isPending ? 'Import…' : 'Importer'}
        </Button>
        <Button type="button" size="sm" variant="secondary" onClick={onDone}>Annuler</Button>
      </div>
    </form>
  )
}

// ── Détail d'un contrat ───────────────────────────────────────────────────────

function ContractDetail({ contract, onView, viewLoading }: {
  contract: ContractOut
  onView: () => void
  viewLoading: boolean
}) {
  const { data: detail, isLoading } = useQuery<ContractDetailOut>({
    queryKey: ['contract-detail', contract.id],
    queryFn: () => contractsApi.detail(contract.id),
    staleTime: 30_000,
  })

  return (
    <div data-testid={`contract-detail-${contract.id}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="m-0">{contract.label}</h3>
          <p className="text-muted m-0 mt-1 text-[12px]">
            {contract.version && <>v{contract.version} · </>}
            importé {relativeDate(contract.imported_at)}
            {contract.updated_at !== contract.imported_at && (
              <> · rafraîchi {relativeDate(contract.updated_at)}</>
            )}
          </p>
          {contract.source_url && (
            <p className="text-muted m-0 mt-0.5 truncate text-[12px] [font-family:var(--font-mono)]">
              {contract.source_url}
            </p>
          )}
        </div>
        <Button variant="icon" size="sm" onClick={onView} disabled={viewLoading}
          title="Visualiser dans Swagger (valider le contrat)"
          data-testid={`contract-view-${contract.id}`}>
          <Eye size={14} weight="duotone" />
        </Button>
      </div>

      <div className="mt-4 mb-2 h-px bg-[var(--color-divider)]" />

      {isLoading ? (
        <TableSkeleton rows={4} columns={2} />
      ) : (
        <ul className="m-0 list-none p-0" data-testid="contract-operations">
          {(detail?.operations ?? []).map((op) => (
            <li key={`${op.method} ${op.path}`}
              className="flex items-baseline gap-3 border-b border-[var(--color-divider)] py-2">
              <MethodTag method={op.method} />
              <span className="shrink-0 text-[13px] [font-family:var(--font-mono)]">{op.path}</span>
              <span className="min-w-0 flex-1 truncate text-[13px] text-ink/[0.6]">
                {op.summary}
              </span>
            </li>
          ))}
          {(detail?.operations ?? []).length === 0 && (
            <p className="text-muted text-[13px]">Aucune opération dans ce contrat.</p>
          )}
        </ul>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function ContractsAdmin() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [showImport, setShowImport] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ContractOut | null>(null)

  const { data: contracts = [], isLoading } = useQuery({
    queryKey: ['contracts'],
    queryFn: () => contractsApi.list(),
    staleTime: 30_000,
  })

  const selected = contracts.find((c) => c.id === selectedId) ?? contracts[0] ?? null

  const refreshMut = useMutation({
    mutationFn: (id: string) => contractsApi.refresh(id),
    onSuccess: (res, id) => {
      void qc.invalidateQueries({ queryKey: ['contracts'] })
      // Le dialogue automate lit contract-detail (opérations + servers) : il faut
      // l'invalider aussi, sinon l'URL construite reste sur l'ancien serveur.
      void qc.invalidateQueries({ queryKey: ['contract-detail', id] })
      // DoD : les opérations disparues encore utilisées par un automate sont
      // signalées — l'appel de l'automate garde son URL figée, mais le
      // sélecteur ne les proposera plus.
      if (res.orphaned_operations.length > 0) {
        const lines = res.orphaned_operations
          .map((o) => `« ${o.operation_id} » utilisée par : ${o.automations.join(', ')}`)
          .join('\n')
        toast(`Contrat mis à jour, mais des opérations ont disparu :\n${lines}`, 'error')
      } else {
        toast('Contrat rafraîchi.', 'success')
      }
    },
    onError: (e: Error) => toast(`Rafraîchissement échoué : ${e.message}`, 'error'),
  })

  // Visualisation Swagger locale du spec.
  const [viewSpec, setViewSpec] = useState<{ label: string; spec: object } | null>(null)
  const [viewLoadingId, setViewLoadingId] = useState<string | null>(null)
  async function openSwagger(id: string, label: string) {
    setViewLoadingId(id)
    try {
      const spec = await contractsApi.spec(id)
      setViewSpec({ label, spec })
    } finally {
      setViewLoadingId(null)
    }
  }

  // Fait tourner la roue pendant le refresh, au moins 1 s (feedback visible).
  const [refreshingId, setRefreshingId] = useState<string | null>(null)
  async function handleRefresh(id: string) {
    setRefreshingId(id)
    const start = Date.now()
    try {
      await refreshMut.mutateAsync(id)
    } finally {
      const elapsed = Date.now() - start
      if (elapsed < 1000) await new Promise((r) => setTimeout(r, 1000 - elapsed))
      setRefreshingId(null)
    }
  }

  const deleteMut = useMutation({
    mutationFn: (id: string) => contractsApi.delete(id),
    onSuccess: () => {
      setDeleteTarget(null)
      void qc.invalidateQueries({ queryKey: ['contracts'] })
    },
  })

  return (
    <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24" data-testid="contracts-admin">
      <SectionHead kicker="Administration" title="Contrats OpenAPI">
        <Button onClick={() => setShowImport((v) => !v)}>
          <Plus size={15} weight="duotone" />
          {showImport ? 'Annuler' : 'Importer'}
        </Button>
      </SectionHead>

      <p className="mb-8 max-w-[64ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        Contrats <strong>partagés entre tous les workspaces</strong> : importez un contrat
        (ex. le RAG) une seule fois, il est disponible dans les automates de chaque workspace.
      </p>

      {isLoading ? (
        <TableSkeleton rows={3} columns={3} />
      ) : contracts.length === 0 && !showImport ? (
        <EmptyState
          testId="contracts-empty"
          message="Aucun contrat importé."
          action={
            <Button onClick={() => setShowImport(true)}>
              <Plus size={15} weight="duotone" /> Importer un contrat
            </Button>
          }
        />
      ) : (
        <div className="grid gap-10 lg:grid-cols-[300px_minmax(0,1fr)]">
          {/* ── Colonne gauche : liste + import ── */}
          <div>
            <ul className="m-0 list-none p-0">
              {contracts.map((c) => {
                const active = selected?.id === c.id
                return (
                  <li key={c.id} className="group relative" data-testid={`contract-row-${c.id}`}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(c.id)}
                      aria-current={active ? 'true' : undefined}
                      className={`w-full rounded-md border-0 px-3 py-2.5 text-left ${
                        active ? 'bg-accent-100' : 'bg-transparent hover:bg-ink/[0.04]'
                      }`}
                    >
                      <span className="block truncate text-[15px] font-[600] [font-family:var(--font-heading)]">
                        {c.label}
                      </span>
                      <span className="text-[12px] text-ink/[0.5]">
                        {c.version ? `v${c.version}` : 'version inconnue'}
                      </span>
                    </button>
                    <span className="absolute right-2 top-1/2 flex -translate-y-1/2 gap-1 opacity-0
                      transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                      {c.source_url && (
                        <Button variant="icon" size="sm"
                          title="Rafraîchir depuis l'URL source"
                          aria-label={`Rafraîchir ${c.label}`}
                          onClick={() => void handleRefresh(c.id)}
                          disabled={refreshingId === c.id}
                          data-testid={`contract-refresh-${c.id}`}>
                          <ArrowClockwise size={14} weight="duotone"
                            className={refreshingId === c.id ? 'animate-spin' : ''} />
                        </Button>
                      )}
                      <Button variant="icon" size="sm" className="text-accent-2-700"
                        title="Supprimer" aria-label={`Supprimer ${c.label}`}
                        onClick={() => setDeleteTarget(c)}
                        data-testid={`contract-delete-${c.id}`}>
                        <Trash size={14} weight="duotone" />
                      </Button>
                    </span>
                  </li>
                )
              })}
            </ul>

            {showImport && <ContractImportForm onDone={() => setShowImport(false)} />}
          </div>

          {/* ── Colonne droite : détail ── */}
          <div>
            {selected ? (
              <ContractDetail
                contract={selected}
                onView={() => void openSwagger(selected.id, selected.label)}
                viewLoading={viewLoadingId === selected.id}
              />
            ) : (
              <p className="text-muted text-[13px]">Sélectionnez un contrat.</p>
            )}
          </div>
        </div>
      )}

      {showImport && contracts.length === 0 && !isLoading && (
        <ContractImportForm onDone={() => setShowImport(false)} />
      )}

      {deleteTarget && (
        <ConfirmDialog
          testId="contract-delete-dialog"
          title="Supprimer le contrat"
          message={`Supprimer « ${deleteTarget.label} » ? Les automates qui l'utilisent gardent leur URL mais perdent le sélecteur d'opération.`}
          confirmLabel="Supprimer le contrat"
          pending={deleteMut.isPending}
          onConfirm={() => deleteMut.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {viewSpec && (
        <div className="dialog-backdrop z-50 !p-4" onClick={() => setViewSpec(null)}>
          <div className="dialog h-full w-full !max-w-5xl" role="dialog" aria-modal="true"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex shrink-0 items-center justify-between">
              <h4 className="dialog-title m-0">Swagger — {viewSpec.label}</h4>
              <button type="button" onClick={() => setViewSpec(null)} title="Fermer"
                aria-label="Fermer"
                className="border-0 bg-transparent p-1 text-ink/[0.4] hover:text-ink">
                <X size={18} weight="bold" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto rounded-md bg-white">
              <Suspense fallback={<p className="text-muted p-8 text-[13px]">Chargement de Swagger…</p>}>
                <SwaggerViewer spec={viewSpec.spec} />
              </Suspense>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

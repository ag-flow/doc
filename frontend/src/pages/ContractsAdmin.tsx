import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Trash2, Upload } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { contractsApi } from '../lib/api'

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
    <div className="mt-3 space-y-2 rounded-md border border-gray-200 bg-gray-50 p-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium mb-1">Libellé</label>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="ag-flow.rag" data-testid="contract-label" />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">URL source (ou coller le JSON ci-dessous)</label>
          <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…/openapi.json" />
        </div>
      </div>
      {!url.trim() && (
        <textarea
          value={jsonText}
          onChange={(e) => setJsonText(e.target.value)}
          className="w-full rounded border border-gray-300 p-2 text-xs font-mono h-28 resize-y"
          placeholder="Coller ici le contrat OpenAPI en JSON…"
        />
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="flex gap-2">
        <Button size="sm" onClick={submit} disabled={importMut.isPending} data-testid="contract-import-submit">
          {importMut.isPending ? 'Import…' : 'Importer'}
        </Button>
        <Button size="sm" variant="secondary" onClick={onDone}>Annuler</Button>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function ContractsAdmin() {
  const qc = useQueryClient()
  const [showImport, setShowImport] = useState(false)

  const { data: contracts = [], isLoading } = useQuery({
    queryKey: ['contracts'],
    queryFn: () => contractsApi.list(),
    staleTime: 30_000,
  })

  const refreshMut = useMutation({
    mutationFn: (id: string) => contractsApi.refresh(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['contracts'] }),
  })

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
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['contracts'] }),
  })

  return (
    <div className="p-8 max-w-3xl" data-testid="contracts-admin">
      <div className="mb-1 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-gray-900">Contrats OpenAPI</h1>
        <Button onClick={() => setShowImport((v) => !v)} className="inline-flex items-center gap-1.5">
          <Upload size={15} />
          {showImport ? 'Annuler' : 'Importer'}
        </Button>
      </div>
      <p className="mb-6 text-sm text-gray-500">
        Contrats <strong>partagés entre tous les workspaces</strong> : importez un contrat
        (ex. le RAG) une seule fois, il est disponible dans les automates de chaque workspace.
      </p>

      {showImport && <ContractImportForm onDone={() => setShowImport(false)} />}

      {isLoading ? (
        <p className="mt-4 text-sm text-gray-400">Chargement…</p>
      ) : contracts.length === 0 ? (
        <p className="mt-4 rounded-xl border border-dashed border-gray-300 bg-white/50 py-12 text-center text-sm text-gray-500">
          Aucun contrat importé.
        </p>
      ) : (
        <div className="mt-4 space-y-2">
          {contracts.map((c) => (
            <div key={c.id} className="flex items-center gap-3 rounded-md border border-gray-200 bg-white px-4 py-2.5" data-testid={`contract-row-${c.id}`}>
              <div className="min-w-0 flex-1">
                <span className="text-sm font-medium">{c.label}</span>
                {c.version && <span className="ml-2 text-xs text-gray-400">v{c.version}</span>}
                {c.source_url && <span className="ml-2 truncate text-xs text-gray-400">{c.source_url}</span>}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {c.source_url && (
                  <button type="button" onClick={() => handleRefresh(c.id)}
                    disabled={refreshingId === c.id}
                    title="Rafraîchir depuis l'URL source"
                    className="rounded p-1 text-gray-400 hover:bg-indigo-50 hover:text-indigo-600 disabled:cursor-default"
                    data-testid={`contract-refresh-${c.id}`}>
                    <RefreshCw size={14} className={refreshingId === c.id ? 'animate-spin' : ''} />
                  </button>
                )}
                <button type="button"
                  onClick={() => { if (confirm(`Supprimer « ${c.label} » ?`)) deleteMut.mutate(c.id) }}
                  className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

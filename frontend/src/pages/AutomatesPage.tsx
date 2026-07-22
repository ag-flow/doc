import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Trash2, Pencil, Plus, FileJson } from 'lucide-react'
import { Button } from '../components/ui/button'
import { AutomationDialog } from '../components/AutomationDialog'
import { AutomationRunHistory } from '../components/AutomationRunHistory'
import { automationsApi, type AutomationOut, type AutomationCreate } from '../lib/api'

// ── Page principale ───────────────────────────────────────────────────────────

export function AutomatesPage() {
  const { wsSlug: ws } = useParams<{ wsSlug: string }>()
  const qc = useQueryClient()

  const [expandedAuto, setExpandedAuto] = useState<string | null>(null)
  const [dialogAuto, setDialogAuto] = useState<AutomationOut | null | 'new'>()
  const [dialogError, setDialogError] = useState<string | null>(null)

  const { data: automations = [], isLoading: aLoading } = useQuery({
    queryKey: ['automations', ws],
    queryFn: () => automationsApi.list(ws!),
    enabled: !!ws,
    staleTime: 15_000,
  })

  const createMut = useMutation({
    mutationFn: (body: AutomationCreate) => automationsApi.create(ws!, body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['automations', ws] }); setDialogAuto(undefined); setDialogError(null) },
    onError: (e: Error) => setDialogError(e.message),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AutomationCreate }) =>
      automationsApi.update(ws!, id, body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['automations', ws] }); setDialogAuto(undefined); setDialogError(null) },
    onError: (e: Error) => setDialogError(e.message),
  })

  const deleteAutoMut = useMutation({
    mutationFn: (id: string) => automationsApi.delete(ws!, id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['automations', ws] }),
  })

  function saveAuto(data: AutomationCreate) {
    setDialogError(null)
    if (dialogAuto === 'new') {
      createMut.mutate(data)
    } else if (dialogAuto) {
      updateMut.mutate({ id: dialogAuto.id, body: data })
    }
  }

  const isSaving = createMut.isPending || updateMut.isPending

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-xl font-bold mb-3">Automates sortants</h1>

      <p className="text-sm text-gray-500 mb-6 max-w-2xl">
        Les automates déclenchent des appels vers des API externes quand un document change
        dans ce workspace. Contrairement aux webhooks qui envoient un payload JSON brut, un
        automate suit un <strong>contrat OpenAPI</strong> importé : vous sélectionnez
        l'opération à appeler, mappez les champs du document sur les paramètres et choisissez
        les événements déclencheurs. Cas d'usage typiques : créer un ticket dans un outil de
        gestion de projet, mettre à jour un statut dans un CRM, ou déclencher un pipeline de
        traitement sans écrire de code d'intégration.
      </p>

      <p className="mb-6 flex items-center gap-2 rounded-md border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-600">
        <FileJson size={15} className="shrink-0 text-gray-400" />
        Les <strong>contrats OpenAPI</strong> sont partagés entre workspaces.
        <Link to="/contracts" className="font-medium text-indigo-600 hover:underline">
          Gérer les contrats →
        </Link>
      </p>

      {/* ── Automates ── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold">Automates</h2>
          <Button size="sm" onClick={() => { setDialogAuto('new'); setDialogError(null) }}>
            <Plus size={13} className="mr-1.5" />
            Nouvel automate
          </Button>
        </div>
        {aLoading ? (
          <p className="text-sm text-gray-400">Chargement…</p>
        ) : automations.length === 0 ? (
          <p className="text-sm text-gray-500">Aucun automate dans ce workspace.</p>
        ) : (
          <div className="space-y-2">
            {automations.map((a) => (
              <div key={a.id} className="rounded-md border border-gray-200 bg-white overflow-hidden">
                <div className="flex items-center gap-3 px-4 py-2.5">
                  <button type="button" onClick={() => setExpandedAuto(expandedAuto === a.id ? null : a.id)}
                    className="text-gray-400 hover:text-gray-700 shrink-0">
                    {expandedAuto === a.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  <div className="flex-1 min-w-0">
                    <span className={`font-medium text-sm ${!a.active ? 'text-gray-400' : ''}`}>{a.label}</span>
                    <span className="ml-2 text-xs text-gray-400">
                      {a.event_codes.map((c) => c.split('.')[2]).join('/') || '—'} · {a.http_method}
                      {a.delay_minutes > 0 && ` · ${a.delay_minutes}min`}
                    </span>
                    {!a.active && <span className="ml-2 text-xs text-amber-600">inactif</span>}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button type="button" onClick={() => { setDialogAuto(a); setDialogError(null) }}
                      className="rounded p-1 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50">
                      <Pencil size={14} />
                    </button>
                    <button type="button"
                      onClick={() => { if (confirm(`Supprimer « ${a.label} » ?`)) deleteAutoMut.mutate(a.id) }}
                      className="rounded p-1 text-gray-400 hover:text-red-500 hover:bg-red-50">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                {expandedAuto === a.id && (
                  <div className="border-t border-gray-100 px-4 py-3">
                    <p className="text-xs font-mono text-gray-500 mb-1 truncate">{a.url}</p>
                    {a.body_template && (
                      <pre className="text-xs bg-gray-50 rounded p-2 overflow-x-auto max-h-24 mb-2">{a.body_template}</pre>
                    )}
                    <p className="text-xs font-semibold text-gray-500 mt-2 mb-1">Historique des exécutions</p>
                    <AutomationRunHistory ws={ws!} automationId={a.id} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {dialogAuto !== undefined && (
        <AutomationDialog
          ws={ws!}
          initial={dialogAuto === 'new' ? null : dialogAuto}
          onSave={saveAuto}
          onClose={() => { setDialogAuto(undefined); setDialogError(null) }}
          saving={isSaving}
          error={dialogError}
        />
      )}
    </div>
  )
}

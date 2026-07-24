import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Trash2, Pencil, Plus, FileJson, Play } from 'lucide-react'
import { Button } from '../components/ui/button'
import { AutomationDialog } from '../components/AutomationDialog'
import { AutomationRunHistory } from '../components/AutomationRunHistory'
import { useToast } from '../components/Toast'
import { automationsApi, type AutomationOut, type AutomationCreate } from '../lib/api'

// ── Page principale ───────────────────────────────────────────────────────────

export function AutomatesPage() {
  const { wsSlug: ws } = useParams<{ wsSlug: string }>()
  const qc = useQueryClient()
  const { toast } = useToast()

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

  const toggleActiveMut = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      automationsApi.update(ws!, id, { active }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['automations', ws] }),
  })

  const [runMsg, setRunMsg] = useState<Record<string, { text: string; err: boolean }>>({})
  const runNextMut = useMutation({
    mutationFn: (id: string) => automationsApi.runNext(ws!, id),
    onSuccess: (res, id) => {
      const label = automations.find((a) => a.id === id)?.label ?? 'Automate'
      let entry: { text: string; err: boolean }
      if (res.status === 'no_pending') {
        entry = { text: 'Aucun event en attente', err: false }
        toast(`« ${label} » : aucun event en attente`, 'info')
      } else if (res.status === 'no_events') {
        entry = { text: 'Aucun event déclencheur', err: true }
        toast(`« ${label} » : aucun event déclencheur sélectionné`, 'info')
      } else {
        const http = res.http_status != null ? `HTTP ${res.http_status}` : (res.status === 'ok' ? 'OK' : 'échec')
        const body = res.body ? res.body.replace(/\s+/g, ' ').trim() : ''
        entry = { text: `Event joué (${http})`, err: res.status === 'failed' }
        if (res.status === 'failed') {
          toast(`« ${label} » — échec de l'appel (${http})${body ? '\n' + body.slice(0, 400) : ''}`, 'error')
        } else {
          toast(`« ${label} » — appel envoyé (${http})`, 'success')
        }
      }
      setRunMsg((m) => ({ ...m, [id]: entry }))
    },
    onError: (e: Error, id) => {
      const label = automations.find((a) => a.id === id)?.label ?? 'Automate'
      toast(`« ${label} » — erreur : ${e.message}`, 'error')
      setRunMsg((m) => ({ ...m, [id]: { text: e.message, err: true } }))
    },
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
                    {runMsg[a.id] && (
                      <span className={`ml-2 text-xs ${runMsg[a.id].err ? 'text-red-600' : 'text-indigo-600'}`}>
                        {runMsg[a.id].text}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {/* Events en attente (au-delà du curseur) */}
                    {a.pending_count > 0 ? (
                      <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700"
                        title="Events non encore évalués (au-delà du curseur)"
                        data-testid={`pending-${a.id}`}>
                        {a.pending_count} en attente
                      </span>
                    ) : (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700"
                        data-testid={`pending-${a.id}`}>
                        à jour
                      </span>
                    )}
                    {/* Jouer l'event courant sans avancer le curseur */}
                    <button type="button" title="Jouer l'event courant (sans avancer le curseur)"
                      onClick={() => runNextMut.mutate(a.id)} disabled={runNextMut.isPending}
                      className="rounded p-1 text-gray-400 hover:bg-indigo-50 hover:text-indigo-600 disabled:opacity-50"
                      data-testid={`run-next-${a.id}`}>
                      <Play size={14} />
                    </button>
                    {/* Toggle d'activation */}
                    <button type="button" role="switch" aria-checked={a.active}
                      onClick={() => toggleActiveMut.mutate({ id: a.id, active: !a.active })}
                      disabled={toggleActiveMut.isPending}
                      title={a.active ? 'Actif — cliquer pour arrêter' : 'Inactif — cliquer pour activer'}
                      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
                        a.active ? 'bg-indigo-600' : 'bg-gray-300'
                      }`}
                      data-testid={`toggle-active-${a.id}`}>
                      <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                        a.active ? 'translate-x-[18px]' : 'translate-x-0.5'
                      }`} />
                    </button>
                    <button type="button" title="Modifier"
                      onClick={() => { setDialogAuto(a); setDialogError(null) }}
                      className="rounded p-1 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50">
                      <Pencil size={14} />
                    </button>
                    <button type="button" title="Supprimer"
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

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CaretDown, CaretRight, Copy, DotsSixVertical, FileCode, PaperPlaneTilt, PencilSimple,
  Play, Plus, SkipBack, SkipForward, Trash,
} from '@phosphor-icons/react'
import { Button } from '../components/ui/button'
import { AutomationDialog } from '../components/AutomationDialog'
import { PushEventsDialog, type PushSelection } from '../components/PushEventsDialog'
import { AutomationRunHistory } from '../components/AutomationRunHistory'
import { useToast } from '../components/Toast'
import { SectionHead } from '../components/SectionHead'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, TableSkeleton } from '../components/ui/states'
import { relativeDate } from '../lib/relativeDate'
import { automationsApi, type AutomationOut, type AutomationCreate } from '../lib/api'

// ── Page principale ───────────────────────────────────────────────────────────

export function AutomatesPage() {
  const qc = useQueryClient()
  const { toast } = useToast()

  const [expandedAuto, setExpandedAuto] = useState<string | null>(null)
  const [dialogAuto, setDialogAuto] = useState<AutomationOut | null | 'new'>()
  const [dialogError, setDialogError] = useState<string | null>(null)

  const { data: automations = [], isLoading: aLoading } = useQuery({
    queryKey: ['automations'],
    queryFn: () => automationsApi.list(),
    staleTime: 15_000,
  })

  const createMut = useMutation({
    mutationFn: (body: AutomationCreate) => automationsApi.create(body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['automations'] }); setDialogAuto(undefined); setDialogError(null) },
    onError: (e: Error) => setDialogError(e.message),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AutomationCreate }) =>
      automationsApi.update(id, body),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['automations'] }); setDialogAuto(undefined); setDialogError(null) },
    onError: (e: Error) => setDialogError(e.message),
  })

  const deleteAutoMut = useMutation({
    mutationFn: (id: string) => automationsApi.delete(id),
    onSuccess: () => {
      setDeleteTarget(null)
      void qc.invalidateQueries({ queryKey: ['automations'] })
    },
  })

  const toggleActiveMut = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      automationsApi.update(id, { active }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['automations'] }),
  })

  const [runMsg, setRunMsg] = useState<Record<string, { text: string; err: boolean }>>({})
  const runNextMut = useMutation({
    mutationFn: (id: string) => automationsApi.runNext(id),
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
      void qc.invalidateQueries({ queryKey: ['automation-runs', id] })
    },
    onError: (e: Error, id) => {
      const label = automations.find((a) => a.id === id)?.label ?? 'Automate'
      toast(`« ${label} » — erreur : ${e.message}`, 'error')
      setRunMsg((m) => ({ ...m, [id]: { text: e.message, err: true } }))
    },
  })

  function toastRun(label: string, res: { status: string; http_status?: number | null; body?: string | null }, suffix = '') {
    if (res.status === 'no_pending') { toast(`« ${label} » : aucun event en attente`, 'info'); return }
    if (res.status === 'no_events') { toast(`« ${label} » : aucun event déclencheur sélectionné`, 'info'); return }
    const http = res.http_status != null ? `HTTP ${res.http_status}` : (res.status === 'ok' ? 'OK' : 'échec')
    const body = res.body ? res.body.replace(/\s+/g, ' ').trim() : ''
    if (res.status === 'failed') toast(`« ${label} » — échec (${http})${suffix}${body ? '\n' + body.slice(0, 400) : ''}`, 'error')
    else toast(`« ${label} » — appel envoyé (${http})${suffix}`, 'success')
  }

  const advanceMut = useMutation({
    mutationFn: (id: string) => automationsApi.advance(id),
    onSuccess: (res, id) => {
      const label = automations.find((a) => a.id === id)?.label ?? 'Automate'
      toastRun(label, res, ' → event suivant')
      void qc.invalidateQueries({ queryKey: ['automations'] })
      void qc.invalidateQueries({ queryKey: ['automation-runs', id] })
    },
    onError: (e: Error, id) => {
      const label = automations.find((a) => a.id === id)?.label ?? 'Automate'
      toast(`« ${label} » — erreur : ${e.message}`, 'error')
    },
  })

  const cursorBackMut = useMutation({
    mutationFn: (id: string) => automationsApi.cursorBack(id),
    onSuccess: (_res, id) => {
      const label = automations.find((a) => a.id === id)?.label ?? 'Automate'
      toast(`« ${label} » — revenu à l'event précédent`, 'info')
      void qc.invalidateQueries({ queryKey: ['automations'] })
    },
  })

  const cloneMut = useMutation({
    mutationFn: (id: string) => automationsApi.clone(id),
    onSuccess: (created) => {
      toast(`« ${created.label} » créé (désactivé)`, 'success')
      void qc.invalidateQueries({ queryKey: ['automations'] })
    },
    onError: (e: Error) => toast(`Clonage échoué : ${e.message}`, 'error'),
  })

  const clearRunsMut = useMutation({
    mutationFn: (id: string) => automationsApi.clearRuns(id),
    onSuccess: (res, id) => {
      setClearRunsTarget(null)
      toast(`Historique vidé (${res.deleted} exécution${res.deleted > 1 ? 's' : ''})`, 'success')
      void qc.invalidateQueries({ queryKey: ['automation-runs', id] })
    },
    onError: (e: Error) => toast(`Échec : ${e.message}`, 'error'),
  })

  const [pushOpen, setPushOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AutomationOut | null>(null)
  const [clearRunsTarget, setClearRunsTarget] = useState<AutomationOut | null>(null)
  const pushEventsMut = useMutation({
    mutationFn: (selections: PushSelection[]) => automationsApi.pushEvents(selections),
    onSuccess: (res) => {
      setPushOpen(false)
      toast(`${res.events} event${res.events > 1 ? 's' : ''} de modification émis`, 'success')
      // Les compteurs « en attente » bougent immédiatement.
      void qc.invalidateQueries({ queryKey: ['automations'] })
    },
    onError: (e: Error) => toast(`Push events échoué : ${e.message}`, 'error'),
  })

  // ── Ordre d'évaluation (drag & drop, propre à CE workspace) ──
  const [dragId, setDragId] = useState<string | null>(null)
  const reorderMut = useMutation({
    mutationFn: (ids: string[]) => automationsApi.reorder(ids),
    onSuccess: (list) => qc.setQueryData(['automations'], list),
    onError: (e: Error) => {
      toast(`Réordonnancement échoué : ${e.message}`, 'error')
      void qc.invalidateQueries({ queryKey: ['automations'] })
    },
  })

  function handleDrop(targetId: string) {
    if (!dragId || dragId === targetId) { setDragId(null); return }
    const ids = automations.map((a) => a.id)
    const from = ids.indexOf(dragId)
    const to = ids.indexOf(targetId)
    if (from < 0 || to < 0) { setDragId(null); return }
    ids.splice(to, 0, ...ids.splice(from, 1))
    setDragId(null)
    // Optimiste : réordonner localement en attendant la réponse.
    qc.setQueryData(['automations'], ids.map((id) => automations.find((a) => a.id === id)!))
    reorderMut.mutate(ids)
  }

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
    <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
      <SectionHead kicker="Administration" title="Automates">
        <Button variant="secondary" onClick={() => setPushOpen(true)} data-testid="push-events-btn">
          <PaperPlaneTilt size={15} weight="duotone" /> Push events
        </Button>
        <Button onClick={() => { setDialogAuto('new'); setDialogError(null) }}>
          <Plus size={15} weight="duotone" /> Nouvel automate
        </Button>
      </SectionHead>

      <p className="mb-4 max-w-[96ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        Les automates déclenchent des appels vers des API externes quand un document change
        dans les workspaces qu'ils couvrent — une règle peut couvrir plusieurs workspaces.
        Contrairement aux webhooks qui envoient un payload JSON brut, un
        automate suit un <strong>contrat OpenAPI</strong> importé : vous sélectionnez
        l'opération à appeler, mappez les champs du document sur les paramètres et choisissez
        les événements déclencheurs. Cas d'usage typiques : créer un ticket dans un outil de
        gestion de projet, mettre à jour un statut dans un CRM, ou déclencher un pipeline de
        traitement sans écrire de code d'intégration.
      </p>

      <p className="mb-8 flex items-center gap-2 text-[13px] text-ink/[0.6]">
        <FileCode size={15} weight="duotone" className="shrink-0 text-accent-700" />
        Les <strong>contrats OpenAPI</strong> sont partagés entre workspaces.
        <Link to="/contracts">Gérer les contrats →</Link>
      </p>

      {/* ── Automates ── */}
      <section>
        {aLoading ? (
          <TableSkeleton rows={4} columns={4} />
        ) : automations.length === 0 ? (
          <EmptyState
            testId="no-automations"
            message="Aucun automate."
            action={
              <Button onClick={() => { setDialogAuto('new'); setDialogError(null) }}>
                <Plus size={15} weight="duotone" /> Nouvel automate
              </Button>
            }
          />
        ) : (
          <ul className="m-0 list-none p-0">
            {automations.map((a) => (
              <li
                key={a.id}
                draggable
                onDragStart={() => setDragId(a.id)}
                onDragEnd={() => setDragId(null)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleDrop(a.id)}
                data-testid={`auto-card-${a.id}`}
                className={`border-b border-[var(--color-divider)] transition-opacity ${
                  dragId === a.id ? 'opacity-50' : ''
                }`}
              >
                <div className="flex items-center gap-2.5 px-1 py-3">
                  <span
                    className="flex shrink-0 cursor-grab items-center text-ink/[0.25] hover:text-ink/[0.6] active:cursor-grabbing"
                    title="Glisser pour changer l'ordre d'évaluation (global, projeté sur chaque workspace)"
                  >
                    <DotsSixVertical size={15} weight="duotone" />
                  </span>
                  <span
                    className="w-6 shrink-0 text-right text-[13px] font-[600] text-ink/[0.38] [font-family:var(--font-heading)]"
                    title="Position d'évaluation"
                  >
                    {String(a.position).padStart(2, '0')}
                  </span>
                  <button
                    type="button"
                    onClick={() => setExpandedAuto(expandedAuto === a.id ? null : a.id)}
                    className="shrink-0 border-0 bg-transparent p-0 text-ink/[0.4] hover:text-ink"
                    aria-expanded={expandedAuto === a.id}
                    aria-label={`Détail de ${a.label}`}
                  >
                    {expandedAuto === a.id
                      ? <CaretDown size={15} weight="duotone" />
                      : <CaretRight size={15} weight="duotone" />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <span className={`text-[16px] font-[600] [font-family:var(--font-heading)] ${!a.active ? 'text-ink/[0.4]' : ''}`}>
                      {a.label}
                    </span>
                    <span className="ml-2.5 text-[12px] text-ink/[0.5]">
                      {a.event_codes.map((c) => c.split('.')[2]).join('/') || '—'} · {a.http_method}
                      {a.delay_minutes > 0 && ` · ${a.delay_minutes}min`}
                    </span>
                    {/* Dernière exécution : code en cyan si succès, magenta si échec. */}
                    {a.last_run_at && (
                      <span className="ml-2.5 text-[12px] text-ink/[0.45]" data-testid={`last-run-${a.id}`}>
                        {relativeDate(a.last_run_at)}
                        {a.last_run_http_status != null && (
                          <span className={a.last_run_status === 'ok' ? 'text-accent-700' : 'text-accent-2-700'}>
                            {' '}· {a.last_run_http_status}
                          </span>
                        )}
                      </span>
                    )}
                    {runMsg[a.id] && (
                      <span className={`ml-2.5 text-[12px] ${runMsg[a.id].err ? 'text-accent-2-700' : 'text-accent-700'}`}>
                        {runMsg[a.id].text}
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {/* Events en attente (au-delà du curseur) — magenta : il y a à faire. */}
                    {a.pending_count > 0 ? (
                      <span className="tag tag-accent-2"
                        title="Events non encore évalués (au-delà du curseur)"
                        data-testid={`pending-${a.id}`}>
                        {a.pending_count} en attente
                      </span>
                    ) : (
                      <span className="tag tag-neutral" data-testid={`pending-${a.id}`}>
                        à jour
                      </span>
                    )}
                    {/* Revenir à l'event précédent (recule le curseur) */}
                    <Button variant="icon" size="sm" title="Revenir à l'event précédent"
                      onClick={() => cursorBackMut.mutate(a.id)} disabled={cursorBackMut.isPending}
                      data-testid={`cursor-back-${a.id}`}>
                      <SkipBack size={14} weight="duotone" />
                    </Button>
                    {/* Jouer l'event courant SANS avancer le curseur (test) */}
                    <Button variant="icon" size="sm" title="Jouer l'event courant (test, sans avancer)"
                      onClick={() => runNextMut.mutate(a.id)} disabled={runNextMut.isPending}
                      data-testid={`run-next-${a.id}`}>
                      <Play size={14} weight="duotone" />
                    </Button>
                    {/* Envoyer l'appel ET passer au suivant (avance le curseur) */}
                    <Button variant="icon" size="sm" title="Envoyer l'appel et passer au suivant"
                      onClick={() => advanceMut.mutate(a.id)} disabled={advanceMut.isPending}
                      data-testid={`advance-${a.id}`}>
                      <SkipForward size={14} weight="duotone" />
                    </Button>
                    {/* Toggle d'activation */}
                    <button type="button" role="switch" aria-checked={a.active}
                      onClick={() => toggleActiveMut.mutate({ id: a.id, active: !a.active })}
                      disabled={toggleActiveMut.isPending}
                      title={a.active ? 'Actif — cliquer pour arrêter' : 'Inactif — cliquer pour activer'}
                      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border-0 transition-colors ${
                        a.active ? 'bg-accent' : 'bg-neutral-300'
                      }`}
                      data-testid={`toggle-active-${a.id}`}>
                      <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-paper shadow-sm transition-transform ${
                        a.active ? 'translate-x-[18px]' : 'translate-x-0.5'
                      }`} />
                    </button>
                    <Button variant="icon" size="sm" title="Cloner (créé désactivé)"
                      onClick={() => cloneMut.mutate(a.id)} disabled={cloneMut.isPending}
                      data-testid={`clone-${a.id}`}>
                      <Copy size={14} weight="duotone" />
                    </Button>
                    <Button variant="icon" size="sm" title="Modifier"
                      onClick={() => { setDialogAuto(a); setDialogError(null) }}>
                      <PencilSimple size={14} weight="duotone" />
                    </Button>
                    <Button variant="icon" size="sm" title="Supprimer" className="text-accent-2-700"
                      onClick={() => setDeleteTarget(a)}>
                      <Trash size={14} weight="duotone" />
                    </Button>
                  </div>
                </div>
                {expandedAuto === a.id && (
                  <div className="px-9 pb-4">
                    <p className="mb-1 truncate text-[12px] text-ink/[0.55] [font-family:var(--font-mono)]">{a.url}</p>
                    {a.body_template && (
                      <pre className="mb-2 max-h-24 overflow-x-auto rounded-md bg-ink/[0.05] p-2 text-[12px]">{a.body_template}</pre>
                    )}
                    <div className="mt-3 mb-1 flex items-center justify-between">
                      <h6 className="m-0 text-ink/[0.5]">Historique des exécutions</h6>
                      <Button variant="ghost" size="sm" className="text-accent-2-700"
                        onClick={() => setClearRunsTarget(a)}
                        disabled={clearRunsMut.isPending}
                        data-testid={`clear-runs-${a.id}`}>
                        Vider l'historique
                      </Button>
                    </div>
                    <AutomationRunHistory automationId={a.id} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {deleteTarget && (
        <ConfirmDialog
          testId="delete-auto-dialog"
          title="Supprimer l'automate"
          message={`Supprimer « ${deleteTarget.label} » ? Son historique d'exécutions part avec lui.`}
          confirmLabel="Supprimer l'automate"
          pending={deleteAutoMut.isPending}
          onConfirm={() => deleteAutoMut.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {clearRunsTarget && (
        <ConfirmDialog
          testId="clear-runs-dialog"
          title="Vider l'historique"
          message={`Effacer l'historique des exécutions de « ${clearRunsTarget.label} » ? Le curseur d'events n'est pas modifié.`}
          confirmLabel="Vider l'historique"
          pending={clearRunsMut.isPending}
          onConfirm={() => clearRunsMut.mutate(clearRunsTarget.id)}
          onCancel={() => setClearRunsTarget(null)}
        />
      )}

      {pushOpen && (
        <PushEventsDialog
          onConfirm={(sel) => pushEventsMut.mutate(sel)}
          onClose={() => setPushOpen(false)}
          pending={pushEventsMut.isPending}
        />
      )}

      {dialogAuto !== undefined && (
        <AutomationDialog
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

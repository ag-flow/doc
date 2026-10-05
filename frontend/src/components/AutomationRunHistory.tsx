import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CaretDown, CaretRight } from '@phosphor-icons/react'
import { automationsApi, type AutomationRunOut } from '../lib/api'

interface Props {
  automationId: string
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
}

// Définition générique de chaque code HTTP, affichée en info-bulle (survol).
const HTTP_HINTS: Record<number, string> = {
  200: 'HTTP 200 OK — la requête a réussi.',
  201: 'HTTP 201 Created — la ressource a été créée.',
  202: 'HTTP 202 Accepted — requête acceptée (traitement asynchrone).',
  204: 'HTTP 204 No Content — succès, sans corps de réponse.',
  301: 'HTTP 301 — redirection permanente (docflow ne suit pas les redirections).',
  302: 'HTTP 302 — redirection (docflow ne suit pas les redirections).',
  307: 'HTTP 307 — redirection temporaire (non suivie).',
  308: 'HTTP 308 — redirection permanente (non suivie).',
  400: 'HTTP 400 Bad Request — requête malformée (syntaxe ou paramètres invalides).',
  401: "HTTP 401 Unauthorized — authentification manquante ou invalide (clé/jeton).",
  403: 'HTTP 403 Forbidden — authentifié mais accès refusé (droits insuffisants).',
  404: 'HTTP 404 Not Found — ressource ou endpoint introuvable (URL erronée ?).',
  405: "HTTP 405 Method Not Allowed — la méthode HTTP n'est pas autorisée sur cette URL.",
  409: "HTTP 409 Conflict — conflit avec l'état actuel de la ressource (ex. doublon).",
  422: 'HTTP 422 Unprocessable Entity — la requête est bien formée mais ses données sont '
    + 'sémantiquement invalides : la cible les a comprises mais refuse de les traiter '
    + '(validation métier échouée, ex. workspace ou champ inexistant).',
  429: 'HTTP 429 Too Many Requests — trop d’appels (limite de débit atteinte).',
  500: 'HTTP 500 Internal Server Error — erreur interne côté cible.',
  502: 'HTTP 502 Bad Gateway — la passerelle/proxy en amont a échoué.',
  503: 'HTTP 503 Service Unavailable — service indisponible (surcharge/maintenance).',
  504: 'HTTP 504 Gateway Timeout — délai dépassé côté passerelle.',
}

function httpHint(code: number | null): string {
  if (code == null) {
    return "Échec avant l'appel HTTP (résolution du secret, corps invalide ou URL refusée)."
  }
  return (
    HTTP_HINTS[code] ??
    (code >= 500
      ? `HTTP ${code} — erreur serveur : la cible a rencontré un problème.`
      : code >= 400
        ? `HTTP ${code} — erreur client : la cible a refusé la requête.`
        : code >= 300
          ? `HTTP ${code} — redirection (non suivie par docflow).`
          : `HTTP ${code}.`)
  )
}

function pretty(body: string | null): string {
  if (!body) return ''
  try {
    return JSON.stringify(JSON.parse(body), null, 2)
  } catch {
    return body
  }
}

export function AutomationRunHistory({ automationId }: Props) {
  const qc = useQueryClient()
  const [replayingId, setReplayingId] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  // On garde 20 runs en base, on affiche les 10 derniers.
  const { data: runs = [], isLoading } = useQuery<AutomationRunOut[]>({
    queryKey: ['automation-runs', automationId],
    queryFn: () => automationsApi.listRuns(automationId, 10),
    staleTime: 10_000,
  })

  const replayMutation = useMutation({
    mutationFn: (runId: string) => automationsApi.replay(automationId, runId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['automation-runs', automationId] })
      setReplayingId(null)
    },
    onError: () => setReplayingId(null),
  })

  if (isLoading) return <p className="text-muted py-2 text-[12px]">Chargement…</p>
  if (!runs.length) return <p className="text-muted py-2 text-[12px]">Aucune exécution.</p>

  return (
    <div className="mt-2 divide-y divide-[var(--color-divider)] rounded-md border border-[var(--color-divider)]">
      {runs.map((run) => {
        const isOpen = expanded === run.id
        const httpLabel = run.http_status != null ? `HTTP ${run.http_status}` : run.status
        return (
          <div key={run.id} data-testid={`run-${run.id}`}>
            <div className="flex items-center gap-2 px-2 py-1.5 text-xs">
              <button type="button" onClick={() => setExpanded(isOpen ? null : run.id)}
                className="border-0 bg-transparent p-0 text-ink/[0.4] hover:text-ink">
                {isOpen ? <CaretDown size={13} weight="duotone" /> : <CaretRight size={13} weight="duotone" />}
              </button>
              <span
                title={httpHint(run.http_status)}
                className={`tag cursor-help ${run.status === 'ok' ? 'tag-accent' : 'tag-accent-2'}`}
              >
                {run.status === 'ok' ? '✓' : '✗'} {httpLabel}
              </span>
              {run.event_code && (
                <span className="text-[10px] text-ink/[0.45] [font-family:var(--font-mono)]">
                  {run.event_code.split('.')[2] ?? run.event_code}
                </span>
              )}
              {run.manual && (
                <span className="tag tag-neutral text-[10px]">manuel</span>
              )}
              <span className="truncate text-ink/[0.45] [font-family:var(--font-mono)]">
                {run.document_ref ? `${run.document_ref.slice(0, 8)}…` : '—'}
                {run.document_version != null ? ` v${run.document_version}` : ''}
              </span>
              <span className="ml-auto text-ink/[0.45]">{fmtDate(run.executed_at)}</span>
              {run.status === 'failed' && (
                <button type="button"
                  disabled={replayingId === run.id || replayMutation.isPending}
                  onClick={() => { setReplayingId(run.id); replayMutation.mutate(run.id) }}
                  className="btn btn-ghost btn-sm">
                  {replayingId === run.id ? 'Rejeu…' : 'Rejouer'}
                </button>
              )}
            </div>

            {isOpen && (
              <div className="space-y-2 border-t border-[var(--color-divider)] bg-surface px-3 py-2 text-[12px]">
                {run.url && (
                  <div>
                    <h6 className="m-0 text-ink/[0.5]">URL</h6>
                    <p className="m-0 break-all text-ink/[0.75] [font-family:var(--font-mono)]">{run.url}</p>
                  </div>
                )}
                <div>
                  <h6 className="m-0 text-ink/[0.5]">Corps envoyé (variables résolues)</h6>
                  <pre className="mt-0.5 max-h-40 overflow-auto rounded-sm bg-paper p-2 text-[11px] [font-family:var(--font-mono)]">
                    {pretty(run.request_body) || '(aucun corps)'}
                  </pre>
                </div>
                <div>
                  <h6 className={`m-0 ${run.status === 'ok' ? 'text-accent-700' : 'text-accent-2-700'}`}>
                    {run.status === 'ok' ? 'Réponse' : 'Erreur / réponse'}
                  </h6>
                  <pre className="mt-0.5 max-h-40 overflow-auto rounded-sm bg-paper p-2 text-[11px] [font-family:var(--font-mono)]">
                    {pretty(run.response_body) || '(aucune réponse)'}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

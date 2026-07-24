import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { automationsApi, type AutomationRunOut } from '../lib/api'

interface Props {
  ws: string
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

export function AutomationRunHistory({ ws, automationId }: Props) {
  const qc = useQueryClient()
  const [replayingId, setReplayingId] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  // On garde 20 runs en base, on affiche les 10 derniers.
  const { data: runs = [], isLoading } = useQuery<AutomationRunOut[]>({
    queryKey: ['automation-runs', ws, automationId],
    queryFn: () => automationsApi.listRuns(ws, automationId, 10),
    staleTime: 10_000,
  })

  const replayMutation = useMutation({
    mutationFn: (runId: string) => automationsApi.replay(ws, automationId, runId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['automation-runs', ws, automationId] })
      setReplayingId(null)
    },
    onError: () => setReplayingId(null),
  })

  if (isLoading) return <p className="py-2 text-xs text-gray-400">Chargement…</p>
  if (!runs.length) return <p className="py-2 text-xs text-gray-400">Aucune exécution.</p>

  return (
    <div className="mt-2 divide-y divide-gray-100 rounded border border-gray-100">
      {runs.map((run) => {
        const isOpen = expanded === run.id
        const httpLabel = run.http_status != null ? `HTTP ${run.http_status}` : run.status
        return (
          <div key={run.id} data-testid={`run-${run.id}`}>
            <div className="flex items-center gap-2 px-2 py-1.5 text-xs">
              <button type="button" onClick={() => setExpanded(isOpen ? null : run.id)}
                className="text-gray-400 hover:text-gray-700">
                {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              </button>
              <span
                title={httpHint(run.http_status)}
                className={`inline-block cursor-help rounded-full px-2 py-0.5 font-medium ${
                  run.status === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
                }`}
              >
                {run.status === 'ok' ? '✓' : '✗'} {httpLabel}
              </span>
              {run.event_code && (
                <span className="font-mono text-[10px] text-gray-400">
                  {run.event_code.split('.')[2] ?? run.event_code}
                </span>
              )}
              {run.manual && (
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">
                  manuel
                </span>
              )}
              <span className="font-mono text-gray-400 truncate">
                {run.document_ref ? `${run.document_ref.slice(0, 8)}…` : '—'}
                {run.document_version != null ? ` v${run.document_version}` : ''}
              </span>
              <span className="ml-auto text-gray-400">{fmtDate(run.executed_at)}</span>
              {run.status === 'failed' && (
                <button type="button"
                  disabled={replayingId === run.id || replayMutation.isPending}
                  onClick={() => { setReplayingId(run.id); replayMutation.mutate(run.id) }}
                  className="rounded px-2 py-0.5 font-medium text-indigo-600 hover:bg-indigo-50 disabled:opacity-40">
                  {replayingId === run.id ? 'Rejeu…' : 'Rejouer'}
                </button>
              )}
            </div>

            {isOpen && (
              <div className="space-y-2 border-t border-gray-100 bg-gray-50 px-3 py-2 text-xs">
                {run.url && (
                  <div>
                    <span className="font-semibold text-gray-500">URL</span>
                    <p className="font-mono text-gray-700 break-all">{run.url}</p>
                  </div>
                )}
                <div>
                  <span className="font-semibold text-gray-500">Corps envoyé (variables résolues)</span>
                  <pre className="mt-0.5 max-h-40 overflow-auto rounded bg-white p-2 font-mono text-[11px] text-gray-700">
                    {pretty(run.request_body) || '(aucun corps)'}
                  </pre>
                </div>
                <div>
                  <span className={`font-semibold ${run.status === 'ok' ? 'text-emerald-600' : 'text-red-600'}`}>
                    {run.status === 'ok' ? 'Réponse' : 'Erreur / réponse'}
                  </span>
                  <pre className="mt-0.5 max-h-40 overflow-auto rounded bg-white p-2 font-mono text-[11px] text-gray-700">
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

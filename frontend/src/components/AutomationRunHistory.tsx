import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { automationsApi, type AutomationRunOut } from '../lib/api'

interface Props {
  ws: string
  automationId: string
}

export function AutomationRunHistory({ ws, automationId }: Props) {
  const qc = useQueryClient()
  const [replayingId, setReplayingId] = useState<string | null>(null)

  const { data: runs = [], isLoading } = useQuery<AutomationRunOut[]>({
    queryKey: ['automation-runs', ws, automationId],
    queryFn: () => automationsApi.listRuns(ws, automationId),
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

  if (isLoading) return <p className="text-xs text-gray-400 py-2">Chargement…</p>
  if (!runs.length) return <p className="text-xs text-gray-400 py-2">Aucune exécution.</p>

  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-gray-500 border-b border-gray-100">
            <th className="py-1 pr-4 font-medium">Document</th>
            <th className="py-1 pr-4 font-medium">Version</th>
            <th className="py-1 pr-4 font-medium">Statut</th>
            <th className="py-1 pr-4 font-medium">Date</th>
            <th className="py-1 font-medium" />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-b border-gray-50 hover:bg-gray-50">
              <td className="py-1 pr-4 font-mono text-gray-500 truncate max-w-[120px]">
                {run.document_ref.slice(0, 8)}…
              </td>
              <td className="py-1 pr-4 text-gray-600">v{run.document_version}</td>
              <td className="py-1 pr-4">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                    run.status === 'ok'
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-red-50 text-red-700'
                  }`}
                >
                  {run.status}
                </span>
              </td>
              <td className="py-1 pr-4 text-gray-400">
                {new Date(run.executed_at).toLocaleString('fr-FR', {
                  dateStyle: 'short',
                  timeStyle: 'short',
                })}
              </td>
              <td className="py-1">
                {run.status === 'failed' && (
                  <button
                    type="button"
                    disabled={replayingId === run.id || replayMutation.isPending}
                    onClick={() => {
                      setReplayingId(run.id)
                      replayMutation.mutate(run.id)
                    }}
                    className="rounded px-2 py-0.5 text-xs font-medium text-indigo-600
                      hover:bg-indigo-50 disabled:opacity-40"
                  >
                    {replayingId === run.id ? 'Rejeu…' : 'Rejouer'}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

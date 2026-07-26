import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { Button } from './ui/button'
import { api, docsApi, type DataBlockOut, type WorkspaceOut } from '../lib/api'

export interface PushSelection {
  workspace_slug: string
  block_slugs: string[]
}

interface Props {
  onConfirm: (selections: PushSelection[]) => void
  onClose: () => void
  pending: boolean
}

/** Blocs d'un workspace coché : cases à cocher (aucune cochée = tous). */
function BlocksNode({
  wsSlug, selected, onToggle,
}: {
  wsSlug: string
  selected: string[]
  onToggle: (slug: string) => void
}) {
  const { data: blocks = [], isLoading } = useQuery<DataBlockOut[]>({
    queryKey: ['blocs', wsSlug],
    queryFn: () => docsApi.getBlocks(wsSlug),
    staleTime: 60_000,
  })
  if (isLoading) return <p className="ml-6 text-xs text-gray-400">Chargement des blocs…</p>
  if (blocks.length === 0) return <p className="ml-6 text-xs text-gray-400">Aucun bloc</p>
  return (
    <div className="ml-6 space-y-0.5 border-l border-gray-100 pl-3">
      {blocks.map((b) => (
        <label key={b.slug} className="flex items-center gap-1.5 text-sm" data-testid={`push-block-${wsSlug}-${b.slug}`}>
          <input type="checkbox" checked={selected.includes(b.slug)}
            onChange={() => onToggle(b.slug)} />
          <span className="truncate">{b.label}</span>
          <span className="ml-auto shrink-0 rounded bg-gray-50 px-1.5 py-0.5 font-mono text-[10px] text-gray-500">
            {b.functional_type_slug}
          </span>
        </label>
      ))}
    </div>
  )
}

/**
 * « Push events » : sélection arbre workspaces → blocs. À la validation, un
 * event de modification synthétique est émis pour CHAQUE document couvert
 * (workspace coché ; blocs cochés = restriction, aucun = tous les blocs).
 */
export function PushEventsDialog({ onConfirm, onClose, pending }: Props) {
  const { data: workspaces = [] } = useQuery<WorkspaceOut[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get<WorkspaceOut[]>('/workspaces'),
    staleTime: 60_000,
  })

  // Sélection PAR workspace : coché + blocs restreints (vide = tous).
  const [checked, setChecked] = useState<Record<string, string[]>>({})

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function toggleWs(slug: string) {
    setChecked((c) => {
      const next = { ...c }
      if (slug in next) delete next[slug]
      else next[slug] = []
      return next
    })
  }

  function toggleBlock(ws: string, slug: string) {
    setChecked((c) => {
      const cur = c[ws] ?? []
      return { ...c, [ws]: cur.includes(slug) ? cur.filter((s) => s !== slug) : [...cur, slug] }
    })
  }

  const selections: PushSelection[] = Object.entries(checked).map(([ws, blocks]) => ({
    workspace_slug: ws,
    block_slugs: blocks,
  }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/40 p-4"
      onClick={onClose}>
      <div className="my-4 flex max-h-[90vh] w-full max-w-lg flex-col gap-4 rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()} data-testid="push-events-dialog">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">Push events</h2>
          <button type="button" onClick={onClose} title="Fermer" aria-label="Fermer"
            className="rounded p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700">
            <X size={18} />
          </button>
        </div>

        <p className="text-sm text-gray-500">
          Émet un event <span className="font-mono text-xs">document.updated</span> pour{' '}
          <strong>chaque document</strong> des workspaces/blocs cochés — les automates qui
          matchent se (re)déclencheront. Aucun bloc coché = tous les blocs du workspace.
        </p>

        <div className="dialog-scroll min-h-0 flex-1 space-y-1.5 overflow-y-auto rounded border border-gray-200 p-2">
          {workspaces.map((w) => {
            const covered = w.slug in checked
            return (
              <div key={w.slug}>
                <label className="flex items-center gap-1.5 text-sm font-medium" data-testid={`push-ws-${w.slug}`}>
                  <input type="checkbox" checked={covered} onChange={() => toggleWs(w.slug)} />
                  <span className="truncate">{w.label}</span>
                  <span className="shrink-0 font-mono text-[10px] text-gray-400">{w.slug}</span>
                </label>
                {covered && (
                  <BlocksNode
                    wsSlug={w.slug}
                    selected={checked[w.slug] ?? []}
                    onToggle={(slug) => toggleBlock(w.slug, slug)}
                  />
                )}
              </div>
            )
          })}
        </div>

        <div className="flex justify-end gap-2 border-t border-gray-100 pt-3">
          <Button variant="secondary" onClick={onClose} disabled={pending}>Annuler</Button>
          <Button
            onClick={() => onConfirm(selections)}
            disabled={pending || selections.length === 0}
            data-testid="push-events-ok"
          >
            {pending ? 'Émission…' : 'OK'}
          </Button>
        </div>
      </div>
    </div>
  )
}

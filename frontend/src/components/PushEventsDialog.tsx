import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from '@phosphor-icons/react'
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
  if (isLoading) return <p className="text-muted ml-6 text-[12px]">Chargement des blocs…</p>
  if (blocks.length === 0) return <p className="text-muted ml-6 text-[12px]">Aucun bloc</p>
  return (
    <div className="ml-6 space-y-0.5 border-l border-[var(--color-divider)] pl-3">
      {blocks.map((b) => (
        <label key={b.slug} className="flex items-center gap-1.5 text-sm" data-testid={`push-block-${wsSlug}-${b.slug}`}>
          <input type="checkbox" checked={selected.includes(b.slug)}
            onChange={() => onToggle(b.slug)} />
          <span className="truncate">{b.label}</span>
          <span className="tag tag-neutral ml-auto shrink-0 text-[10px]">
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
    <div className="dialog-backdrop z-50 overflow-y-auto" onClick={onClose}>
      <div className="dialog my-4 max-h-[90vh] w-full !max-w-lg" role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()} data-testid="push-events-dialog">
        <div className="flex items-center justify-between">
          <h4 className="dialog-title m-0">Push events</h4>
          <button type="button" onClick={onClose} title="Fermer" aria-label="Fermer"
            className="border-0 bg-transparent p-1 text-ink/[0.4] transition-colors hover:text-ink">
            <X size={18} weight="bold" />
          </button>
        </div>

        <p className="dialog-body m-0">
          Émet un event <span className="text-[12px] text-accent-700 [font-family:var(--font-mono)]">document.refreshed</span> pour{' '}
          <strong>chaque document</strong> des workspaces/blocs cochés. Seuls les automates
          abonnés à <strong>« Document rafraîchi »</strong> se re-déclencheront — les abonnés
          aux modifications normales ne réagissent pas. Aucun bloc coché = tous les blocs.
        </p>

        <div className="dialog-scroll min-h-0 flex-1 space-y-1.5 overflow-y-auto rounded-md border border-[var(--color-divider)] p-2">
          {workspaces.map((w) => {
            const covered = w.slug in checked
            return (
              <div key={w.slug}>
                <label className="flex items-center gap-1.5 text-sm font-medium" data-testid={`push-ws-${w.slug}`}>
                  <input type="checkbox" checked={covered} onChange={() => toggleWs(w.slug)} />
                  <span className="truncate">{w.label}</span>
                  <span className="shrink-0 text-[10px] text-accent-700 [font-family:var(--font-mono)]">{w.slug}</span>
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

        <div className="dialog-actions m-0 border-t border-[var(--color-divider)] pt-3">
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

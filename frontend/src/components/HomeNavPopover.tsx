import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Home } from 'lucide-react'
import { type DataBlockOut, type WorkspaceOut, api, docsApi } from '../lib/api'

/** Icône maison du fil d'Ariane : ouvre l'arbre workspaces → blocs pour une
 *  navigation rapide. Les blocs d'un workspace sont chargés au dépliage. */
export function HomeNavPopover() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [blocks, setBlocks] = useState<Record<string, DataBlockOut[]>>({})
  const rootRef = useRef<HTMLDivElement>(null)

  const { data: workspaces = [] } = useQuery<WorkspaceOut[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get<WorkspaceOut[]>('/workspaces'),
    enabled: open,
  })

  // Fermeture au clic extérieur / Échap
  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  function toggleWs(slug: string) {
    setExpanded((p) => ({ ...p, [slug]: !p[slug] }))
    if (!blocks[slug]) {
      docsApi
        .getBlocks(slug)
        .then((b) => setBlocks((p) => ({ ...p, [slug]: b })))
        .catch(() => setBlocks((p) => ({ ...p, [slug]: [] })))
    }
  }

  function go(path: string) {
    setOpen(false)
    void navigate(path)
  }

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        title="Naviguer (workspaces et blocs)"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center rounded-md p-1 text-gray-400 hover:text-gray-700
          hover:bg-gray-100 transition-colors"
        data-testid="home-nav-btn"
      >
        <Home size={15} />
      </button>

      {open && (
        <div
          className="absolute left-0 top-8 z-40 max-h-96 w-72 overflow-y-auto rounded-lg
            border border-gray-200 bg-white py-1 shadow-lg"
          data-testid="home-nav-popover"
        >
          {workspaces.length === 0 && (
            <p className="px-3 py-2 text-xs text-gray-400">Aucun workspace.</p>
          )}
          {workspaces.map((w) => (
            <div key={w.slug}>
              <div className="flex items-center gap-1 px-2 py-1.5 hover:bg-gray-50">
                <button
                  type="button"
                  onClick={() => toggleWs(w.slug)}
                  className="p-0.5 text-gray-400 hover:text-gray-700"
                  data-testid={`home-nav-expand-${w.slug}`}
                >
                  {expanded[w.slug] ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </button>
                <button
                  type="button"
                  onClick={() => go(`/ws/${w.slug}/blocs`)}
                  className="flex-1 truncate text-left text-sm text-gray-700 hover:text-indigo-700"
                  data-testid={`home-nav-ws-${w.slug}`}
                >
                  {w.label}
                </button>
              </div>
              {expanded[w.slug] && (
                <div className="pb-1">
                  {blocks[w.slug] === undefined && (
                    <p className="pl-9 py-1 text-xs text-gray-400">Chargement…</p>
                  )}
                  {blocks[w.slug]?.length === 0 && (
                    <p className="pl-9 py-1 text-xs text-gray-400">Aucun bloc.</p>
                  )}
                  {blocks[w.slug]?.map((b) => (
                    <button
                      key={b.slug}
                      type="button"
                      onClick={() => go(`/ws/${w.slug}/blocs/${b.slug}/documents`)}
                      className="block w-full truncate pl-9 pr-3 py-1 text-left text-sm
                        text-gray-500 hover:bg-indigo-50 hover:text-indigo-700"
                      data-testid={`home-nav-block-${w.slug}-${b.slug}`}
                    >
                      {b.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

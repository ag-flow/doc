import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { House, FolderOpen, Folder } from '@phosphor-icons/react'
import { type DataBlockOut, type WorkspaceOut, api, docsApi } from '../lib/api'

/** Icône maison de l'en-tête : ouvre l'arbre workspaces → blocs pour une
 *  navigation rapide. Les blocs d'un workspace sont chargés au dépliage. */
export function HomeNavPopover() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [blocks, setBlocks] = useState<Record<string, DataBlockOut[]>>({})
  const rootRef = useRef<HTMLSpanElement>(null)

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
    <span ref={rootRef}>
      <button
        type="button"
        title="Naviguer (workspaces et blocs)"
        onClick={() => setOpen((v) => !v)}
        className="header-icon"
        data-testid="home-nav-btn"
      >
        <House size={17} weight="duotone" />
      </button>

      {open && (
        <div className="nav-panel" data-testid="home-nav-popover">
          <div className="nav-panel-kicker">Aller à un bloc</div>
          {workspaces.length === 0 && (
            <p className="text-muted text-[13px]">Aucun workspace.</p>
          )}
          {workspaces.map((w) => (
            <div key={w.slug}>
              <button
                type="button"
                onClick={() => toggleWs(w.slug)}
                className="nav-panel-ws"
                data-testid={`home-nav-expand-${w.slug}`}
              >
                {expanded[w.slug]
                  ? <FolderOpen size={16} weight="duotone" className="nav-panel-icon" />
                  : <Folder size={16} weight="duotone" className="nav-panel-icon" />}
                <span className="truncate">{w.label}</span>
              </button>
              {expanded[w.slug] && (
                <>
                  {blocks[w.slug] === undefined && (
                    <p className="nav-panel-block text-muted">Chargement…</p>
                  )}
                  {blocks[w.slug]?.length === 0 && (
                    <p className="nav-panel-block text-muted">Aucun bloc.</p>
                  )}
                  {blocks[w.slug]?.map((b) => (
                    <button
                      key={b.slug}
                      type="button"
                      onClick={() => go(`/ws/${w.slug}/blocs/${b.slug}/documents`)}
                      className="nav-panel-block"
                      data-testid={`home-nav-block-${w.slug}-${b.slug}`}
                    >
                      <span className="nav-panel-tree">└</span>
                      <span className="truncate">{b.label}</span>
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => go(`/ws/${w.slug}/blocs`)}
                    className="nav-panel-block"
                    data-testid={`home-nav-ws-${w.slug}`}
                  >
                    <span className="nav-panel-tree">└</span>
                    <span className="text-accent-700">Tous les blocs →</span>
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </span>
  )
}

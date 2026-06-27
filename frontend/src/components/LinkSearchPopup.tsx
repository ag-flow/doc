import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, FolderOpen, Search } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import {
  api,
  docsApi,
  referencesApi,
  type DataBlockOut,
  type DocumentOut,
  type DocumentSearchResult,
  type WorkspaceOut,
} from '../lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

type DocNode = { doc: DocumentOut; children: DocNode[] }

function buildTree(docs: DocumentOut[]): DocNode[] {
  const map = new Map<string, DocNode>()
  docs.forEach((d) => map.set(d.doc_technical_key, { doc: d, children: [] }))
  const roots: DocNode[] = []
  docs.forEach((d) => {
    const node = map.get(d.doc_technical_key)!
    if (d.parent_id && map.has(d.parent_id)) {
      map.get(d.parent_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  })
  return roots
}

// ── Nœud d'arbre ─────────────────────────────────────────────────────────────

function DocTreeNode({
  node,
  depth,
  onSelect,
}: {
  node: DocNode
  depth: number
  onSelect: (doc: DocumentSearchResult) => void
}) {
  const [open, setOpen] = useState(false)
  const hasChildren = node.children.length > 0

  return (
    <div>
      <div
        className="flex items-center hover:bg-blue-50 rounded transition-colors"
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
      >
        <span className="w-5 shrink-0 flex items-center justify-center">
          {hasChildren && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setOpen((o) => !o) }}
              className="text-gray-400 hover:text-gray-600"
            >
              {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
          )}
        </span>
        <button
          type="button"
          className="flex-1 text-left py-1.5 pr-3 text-sm text-gray-800 truncate"
          onClick={() =>
            onSelect({
              id: node.doc.doc_technical_key,
              title: node.doc.title,
              type: node.doc.functional_type_slug,
              bloc: node.doc.data_block_ref,
            })
          }
        >
          {node.doc.title}
          {node.doc.functional_type_slug && (
            <span className="ml-1.5 text-xs text-gray-400">{node.doc.functional_type_slug}</span>
          )}
        </button>
      </div>
      {open &&
        node.children.map((child) => (
          <DocTreeNode
            key={child.doc.doc_technical_key}
            node={child}
            depth={depth + 1}
            onSelect={onSelect}
          />
        ))}
    </div>
  )
}

// ── Arbre d'un workspace (lazy-loadé à l'expansion) ──────────────────────────

function WorkspaceTree({
  wsSlug,
  onSelect,
}: {
  wsSlug: string
  onSelect: (doc: DocumentSearchResult) => void
}) {
  const { data: blocs = [], isLoading: blocsLoading } = useQuery<DataBlockOut[]>({
    queryKey: ['blocs', wsSlug],
    queryFn: () => docsApi.getBlocks(wsSlug),
    staleTime: 60_000,
  })
  const { data: docs = [], isLoading: docsLoading } = useQuery<DocumentOut[]>({
    queryKey: ['ws-documents', wsSlug],
    queryFn: () => docsApi.listDocuments(wsSlug),
    staleTime: 60_000,
  })

  if (blocsLoading || docsLoading) {
    return <div className="px-6 py-2 text-xs text-gray-400">Chargement…</div>
  }
  if (docs.length === 0) {
    return <div className="px-6 py-2 text-xs text-gray-400">Aucun document dans ce workspace.</div>
  }

  const rootsByBloc = new Map<string, DocNode[]>(blocs.map((b) => [b.id, []]))
  buildTree(docs).forEach((node) => {
    rootsByBloc.get(node.doc.data_block_ref)?.push(node)
  })

  return (
    <div className="pb-1">
      {blocs.map((b) => {
        const roots = rootsByBloc.get(b.id) ?? []
        if (roots.length === 0) return null
        return (
          <div key={b.id} className="mt-1">
            <div className="px-5 py-1 text-xs font-semibold text-gray-500 uppercase tracking-wide">
              {b.label}
            </div>
            {roots.map((node) => (
              <DocTreeNode
                key={node.doc.doc_technical_key}
                node={node}
                depth={0}
                onSelect={onSelect}
              />
            ))}
          </div>
        )
      })}
    </div>
  )
}

// ── Popup principal ───────────────────────────────────────────────────────────

interface LinkSearchPopupProps {
  wsSlug: string
  onSelect: (doc: DocumentSearchResult) => void
  onClose: () => void
}

export function LinkSearchPopup({ wsSlug, onSelect, onClose }: LinkSearchPopupProps) {
  const [mode, setMode] = useState<'search' | 'browse'>('search')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<DocumentSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(0)
  const [expandedWs, setExpandedWs] = useState<Set<string>>(new Set([wsSlug]))
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: workspaces = [] } = useQuery<WorkspaceOut[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get<WorkspaceOut[]>('/workspaces'),
    staleTime: 60_000,
    enabled: mode === 'browse',
  })

  useEffect(() => {
    if (mode === 'search') inputRef.current?.focus()
  }, [mode])

  useEffect(() => {
    if (!query.trim()) { setResults([]); return }
    setLoading(true)
    const t = setTimeout(() => {
      referencesApi
        .searchDocuments(wsSlug, query)
        .then((r) => { setResults(r); setSelected(0) })
        .catch(() => setResults([]))
        .finally(() => setLoading(false))
    }, 200)
    return () => clearTimeout(t)
  }, [query, wsSlug])

  const handleKey = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose() }
      if (e.key === 'ArrowDown') { e.preventDefault(); setSelected((s) => Math.min(s + 1, results.length - 1)) }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSelected((s) => Math.max(s - 1, 0)) }
      if (e.key === 'Enter' && results[selected]) { e.preventDefault(); onSelect(results[selected]) }
    },
    [results, selected, onClose, onSelect],
  )

  const toggleWs = (slug: string) =>
    setExpandedWs((prev) => {
      const next = new Set(prev)
      next.has(slug) ? next.delete(slug) : next.add(slug)
      return next
    })

  const sortedWs = [...workspaces].sort((a, b) =>
    a.slug === wsSlug ? -1 : b.slug === wsSlug ? 1 : a.label.localeCompare(b.label),
  )

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/20"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg bg-white rounded-xl shadow-2xl border border-gray-200 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Onglets */}
        <div className="flex border-b border-gray-100">
          {(
            [
              { key: 'search', label: 'Rechercher', Icon: Search },
              { key: 'browse', label: 'Parcourir', Icon: FolderOpen },
            ] as const
          ).map(({ key, label, Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setMode(key)}
              className={[
                'flex-1 flex items-center justify-center gap-1.5 py-2.5 text-sm font-medium transition-colors',
                mode === key
                  ? 'text-blue-600 border-b-2 border-blue-500'
                  : 'text-gray-500 hover:text-gray-700',
              ].join(' ')}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>

        {/* Mode Rechercher */}
        {mode === 'search' && (
          <>
            <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
              <Search size={16} className="text-gray-400 shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Rechercher un document par titre…"
                className="flex-1 text-sm outline-none placeholder:text-gray-400"
              />
              {loading && <span className="text-xs text-gray-400 shrink-0">…</span>}
            </div>
            <div className="max-h-72 overflow-y-auto">
              {!query.trim() && (
                <p className="px-4 py-3 text-sm text-gray-400">Tapez pour rechercher dans ce workspace…</p>
              )}
              {query.trim() && !loading && results.length === 0 && (
                <p className="px-4 py-3 text-sm text-gray-400">Aucun document trouvé.</p>
              )}
              {results.map((r, i) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => onSelect(r)}
                  className={[
                    'w-full text-left px-4 py-2.5 flex flex-col gap-0.5 transition-colors',
                    i === selected ? 'bg-blue-50' : 'hover:bg-gray-50',
                  ].join(' ')}
                >
                  <span className="text-sm font-medium text-gray-800 truncate">{r.title}</span>
                  {r.type && <span className="text-xs text-gray-400">{r.type}</span>}
                </button>
              ))}
            </div>
            <div className="px-4 py-2 border-t border-gray-100 text-xs text-gray-400">
              ↑↓ naviguer · Entrée sélectionner · Échap fermer
            </div>
          </>
        )}

        {/* Mode Parcourir */}
        {mode === 'browse' && (
          <div className="max-h-96 overflow-y-auto">
            {sortedWs.length === 0 && (
              <div className="px-4 py-3 text-sm text-gray-400">Chargement des workspaces…</div>
            )}
            {sortedWs.map((ws) => {
              const isExpanded = expandedWs.has(ws.slug)
              return (
                <div key={ws.slug}>
                  <button
                    type="button"
                    onClick={() => toggleWs(ws.slug)}
                    className="w-full flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors border-b border-gray-50"
                  >
                    {isExpanded
                      ? <ChevronDown size={14} className="shrink-0 text-gray-400" />
                      : <ChevronRight size={14} className="shrink-0 text-gray-400" />}
                    <span className="flex-1 text-left truncate">{ws.label}</span>
                    {ws.slug === wsSlug && (
                      <span className="text-xs font-normal text-blue-500 shrink-0">courant</span>
                    )}
                  </button>
                  {isExpanded && <WorkspaceTree wsSlug={ws.slug} onSelect={onSelect} />}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

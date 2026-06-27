import { useEffect, useImperativeHandle, forwardRef, useRef, useState, useCallback } from 'react'
import { BlockNoteSchema, defaultBlockSpecs } from '@blocknote/core'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import {
  SuggestionMenuController,
  getDefaultReactSlashMenuItems,
} from '@blocknote/react'
import '@blocknote/mantine/style.css'
import { Link, Search } from 'lucide-react'
import { MermaidBlock } from './MermaidBlock'
import {
  parseMarkdownWithMermaid,
  serializeMarkdownWithMermaid,
  type MarkdownEditorApi,
} from '../lib/mermaidMarkdown'
import { referencesApi, type DocumentSearchResult } from '../lib/api'

function filterItems<T extends { title: string; aliases?: string[] }>(
  items: T[],
  query: string,
): T[] {
  const q = query.toLowerCase().trim()
  if (!q) return items
  return items.filter(
    (item) =>
      item.title.toLowerCase().includes(q) ||
      item.aliases?.some((a) => a.toLowerCase().includes(q)),
  )
}

const schema = BlockNoteSchema.create({
  blockSpecs: { ...defaultBlockSpecs, mermaid: MermaidBlock() },
})

export interface MarkdownEditorHandle {
  getMarkdown: () => Promise<string>
}

interface MarkdownEditorProps {
  initialContent: string
  onDirty: () => void
  wsSlug?: string
}

// ── Popup de recherche de lien ────────────────────────────────────────────────

interface LinkSearchPopupProps {
  wsSlug: string
  onSelect: (doc: DocumentSearchResult) => void
  onClose: () => void
}

function LinkSearchPopup({ wsSlug, onSelect, onClose }: LinkSearchPopupProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<DocumentSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    if (!query.trim()) { setResults([]); return }
    setLoading(true)
    const timer = setTimeout(() => {
      referencesApi.searchDocuments(wsSlug, query)
        .then((r) => { setResults(r); setSelected(0) })
        .catch(() => setResults([]))
        .finally(() => setLoading(false))
    }, 200)
    return () => clearTimeout(timer)
  }, [query, wsSlug])

  const handleKey = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose() }
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected((s) => Math.min(s + 1, results.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelected((s) => Math.max(s - 1, 0)) }
    if (e.key === 'Enter' && results[selected]) { e.preventDefault(); onSelect(results[selected]) }
  }, [results, selected, onClose, onSelect])

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/20"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md bg-white rounded-xl shadow-2xl border border-gray-200 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
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
          {loading && (
            <span className="text-xs text-gray-400 shrink-0">Recherche…</span>
          )}
        </div>
        <div className="max-h-72 overflow-y-auto">
          {results.length === 0 && query.trim() && !loading && (
            <p className="px-4 py-3 text-sm text-gray-400">Aucun document trouvé.</p>
          )}
          {results.length === 0 && !query.trim() && (
            <p className="px-4 py-3 text-sm text-gray-400">Tapez pour rechercher…</p>
          )}
          {results.map((doc, i) => (
            <button
              key={doc.id}
              type="button"
              onClick={() => onSelect(doc)}
              className={[
                'w-full text-left px-4 py-2.5 flex flex-col gap-0.5 transition-colors',
                i === selected ? 'bg-blue-50' : 'hover:bg-gray-50',
              ].join(' ')}
            >
              <span className="text-sm font-medium text-gray-800 truncate">{doc.title}</span>
              {(doc.type || doc.bloc) && (
                <span className="text-xs text-gray-400">
                  {[doc.type, doc.bloc ? `bloc ${doc.bloc.slice(0, 8)}…` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="px-4 py-2 border-t border-gray-100 text-xs text-gray-400">
          ↑↓ naviguer · Entrée sélectionner · Échap fermer
        </div>
      </div>
    </div>
  )
}

// ── Éditeur principal ─────────────────────────────────────────────────────────

export const MarkdownEditor = forwardRef<MarkdownEditorHandle, MarkdownEditorProps>(
  ({ initialContent, onDirty, wsSlug }, ref) => {
    const editor = useCreateBlockNote({ schema })
    const loadedRef = useRef(false)
    const settledRef = useRef(false)
    const onDirtyRef = useRef(onDirty)
    onDirtyRef.current = onDirty

    const [linkSearchOpen, setLinkSearchOpen] = useState(false)

    useEffect(() => {
      if (loadedRef.current) return
      loadedRef.current = true
      let cancelled = false
      void (async () => {
        const api = editor as unknown as MarkdownEditorApi
        const blocks = await parseMarkdownWithMermaid(api, initialContent ?? '')
        if (cancelled) return
        if (blocks.length > 0) {
          editor.replaceBlocks(editor.document, blocks as never)
        }
        setTimeout(() => { if (!cancelled) settledRef.current = true }, 0)
      })()
      return () => { cancelled = true }
    }, [editor, initialContent])

    useImperativeHandle(ref, () => ({
      getMarkdown: () => serializeMarkdownWithMermaid(editor as unknown as MarkdownEditorApi),
    }), [editor])

    const handleLinkSelect = useCallback((doc: DocumentSearchResult) => {
      setLinkSearchOpen(false)
      editor.createLink(`docflow://doc/${doc.id}`, doc.title)
    }, [editor])

    // Item personnalisé dans le menu slash
    const linkSlashItem = {
      title: 'Lien document',
      subtext: 'Insérer un lien vers un document',
      onItemClick: () => setLinkSearchOpen(true),
      aliases: ['link', 'lien', 'référence', 'ref'],
      group: 'Insérer',
      icon: <Link size={18} />,
      key: 'link-document',
    }

    return (
      <div className="rounded border border-gray-200 bg-white" data-testid="markdown-editor">
        <BlockNoteView
          editor={editor}
          slashMenu={false}
          onChange={() => { if (settledRef.current) onDirtyRef.current() }}
        >
          {wsSlug && (
            <SuggestionMenuController
              triggerCharacter="/"
              getItems={async (query) =>
                filterItems(
                  [linkSlashItem, ...getDefaultReactSlashMenuItems(editor)],
                  query,
                )
              }
            />
          )}
          {!wsSlug && (
            <SuggestionMenuController
              triggerCharacter="/"
              getItems={async (query) =>
                filterItems(getDefaultReactSlashMenuItems(editor), query)
              }
            />
          )}
        </BlockNoteView>

        {linkSearchOpen && wsSlug && (
          <LinkSearchPopup
            wsSlug={wsSlug}
            onSelect={handleLinkSelect}
            onClose={() => setLinkSearchOpen(false)}
          />
        )}
      </div>
    )
  },
)
MarkdownEditor.displayName = 'MarkdownEditor'

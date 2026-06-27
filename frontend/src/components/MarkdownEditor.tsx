import { useEffect, useImperativeHandle, forwardRef, useRef, useState, useCallback } from 'react'
import { BlockNoteSchema, defaultBlockSpecs } from '@blocknote/core'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import {
  SuggestionMenuController,
  getDefaultReactSlashMenuItems,
} from '@blocknote/react'
import '@blocknote/mantine/style.css'
import { Link } from 'lucide-react'
import { MermaidBlock } from './MermaidBlock'
import {
  parseMarkdownWithMermaid,
  serializeMarkdownWithMermaid,
  type MarkdownEditorApi,
} from '../lib/mermaidMarkdown'
import { type DocumentSearchResult } from '../lib/api'
import { LinkSearchPopup } from './LinkSearchPopup'

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

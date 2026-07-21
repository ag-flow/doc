import { useEffect, useImperativeHandle, forwardRef, useRef, useState, useCallback } from 'react'
import { BlockNoteSchema, defaultBlockSpecs } from '@blocknote/core'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import {
  SuggestionMenuController,
  getDefaultReactSlashMenuItems,
} from '@blocknote/react'
import '@blocknote/mantine/style.css'
import { Link, Table } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { MermaidBlock } from './MermaidBlock'
import { DatasetBlock } from './DatasetBlock'
import {
  parseMarkdownWithBlocks,
  serializeMarkdownWithBlocks,
  type BlockMarkdownEditorApi,
} from '../lib/datasetMarkdown'
import { type DocumentSearchResult } from '../lib/api'
import { datasetsApi } from '../lib/datasetsApi'
import { makeUploadFile, resolveArtifactUrl } from '../lib/artifacts'
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
  blockSpecs: { ...defaultBlockSpecs, mermaid: MermaidBlock(), dataset: DatasetBlock() },
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
    const { t } = useTranslation()
    // uploadFile : collage/drop d'une image → POST artefact, l'URL retournée est
    // stockée dans le bloc image et sérialisée en markdown ![nom](url).
    // resolveFileUrl : l'endpoint est authentifié Bearer, l'affichage passe par
    // un fetch authentifié + object URL (une <img> ne porte pas de header).
    const editor = useCreateBlockNote(
      {
        schema,
        uploadFile: wsSlug ? makeUploadFile(wsSlug) : undefined,
        resolveFileUrl: resolveArtifactUrl,
      },
      [wsSlug],
    )
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
        const api = editor as unknown as BlockMarkdownEditorApi
        const blocks = await parseMarkdownWithBlocks(api, initialContent ?? '')
        if (cancelled) return
        if (blocks.length > 0) {
          editor.replaceBlocks(editor.document, blocks as never)
        }
        setTimeout(() => { if (!cancelled) settledRef.current = true }, 0)
      })()
      return () => { cancelled = true }
    }, [editor, initialContent])

    useImperativeHandle(ref, () => ({
      getMarkdown: () => serializeMarkdownWithBlocks(editor as unknown as BlockMarkdownEditorApi),
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

    // Crée un dataset vide et insère son bloc de référence à la position courante.
    const insertDataset = useCallback(async () => {
      if (!wsSlug) return
      const slug = `dataset-${Date.now().toString(36)}`
      const ds = await datasetsApi.createDataset(wsSlug, { slug, label: t('dataset.defaultLabel') })
      editor.insertBlocks(
        [{ type: 'dataset', props: { datasetId: ds.id } }] as never,
        editor.getTextCursorPosition().block,
        'after',
      )
    }, [editor, wsSlug, t])

    const datasetSlashItem = {
      title: t('dataset.slashTitle'),
      subtext: t('dataset.slashHint'),
      onItemClick: () => { void insertDataset() },
      aliases: ['dataset', 'tableau', 'table', 'grille', 'données'],
      group: 'Insérer',
      icon: <Table size={18} />,
      key: 'dataset',
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
                  [linkSlashItem, datasetSlashItem, ...getDefaultReactSlashMenuItems(editor)],
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

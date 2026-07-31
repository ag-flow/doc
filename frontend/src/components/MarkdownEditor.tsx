import { useEffect, useImperativeHandle, forwardRef, useRef, useState, useCallback } from 'react'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import {
  SuggestionMenuController,
  FilePanelController,
  getDefaultReactSlashMenuItems,
  type DefaultReactSuggestionItem,
} from '@blocknote/react'
import '@blocknote/mantine/style.css'
import { Link } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  docflowSchema,
  parseMarkdownWithCodecs,
  serializeMarkdownWithCodecs,
  slashItemsFromRegistry,
  type CodecEditorApi,
  type SlashContext,
} from '../lib/blockCodecs'
import { type DocumentSearchResult } from '../lib/api'
import { makeUploadFile, resolveArtifactUrl } from '../lib/artifacts'
import { LinkSearchPopup } from './LinkSearchPopup'
import { EditorFilePanel } from './editorFilePanel'
import { useToast } from './Toast'

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

export interface MarkdownEditorHandle {
  getMarkdown: () => Promise<string>
}

/**
 * Collage : garder le HTML quand il existe. Le défaut BlockNote
 * (`prioritizeMarkdownOverHTML: true`) jette le `text/html` dès que le
 * `text/plain` « ressemble à du markdown » — un tableau copié depuis
 * Confluence/Excel/Sheets arrive avec les deux saveurs et son texte brut
 * déclenche l'heuristique : on collait du texte au lieu du tableau. Avec le
 * HTML prioritaire, ces tableaux collent en vrais blocs table ; un texte brut
 * SEUL (éditeur de code, fichier .md) reste interprété comme markdown.
 */
export function docflowPasteHandler({
  defaultPasteHandler,
}: {
  defaultPasteHandler: (context?: {
    prioritizeMarkdownOverHTML?: boolean
    plainTextAsMarkdown?: boolean
  }) => boolean | undefined
}): boolean | undefined {
  return defaultPasteHandler({ prioritizeMarkdownOverHTML: false })
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
    const { toast } = useToast()
    // uploadFile : collage/drop d'une image → POST artefact, l'URL retournée est
    // stockée dans le bloc image et sérialisée en markdown ![nom](url).
    // resolveFileUrl : l'endpoint est authentifié Bearer, l'affichage passe par
    // un fetch authentifié + object URL (une <img> ne porte pas de header).
    const editor = useCreateBlockNote(
      {
        schema: docflowSchema,
        uploadFile: wsSlug ? makeUploadFile(wsSlug) : undefined,
        resolveFileUrl: resolveArtifactUrl,
        pasteHandler: docflowPasteHandler,
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
        const api = editor as unknown as CodecEditorApi
        const blocks = await parseMarkdownWithCodecs(api, initialContent ?? '')
        if (cancelled) return
        if (blocks.length > 0) {
          editor.replaceBlocks(editor.document, blocks as never)
        }
        setTimeout(() => { if (!cancelled) settledRef.current = true }, 0)
      })()
      return () => { cancelled = true }
    }, [editor, initialContent])

    useImperativeHandle(ref, () => ({
      getMarkdown: () => serializeMarkdownWithCodecs(editor as unknown as CodecEditorApi),
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

    // Items des composants custom, dérivés du registre de codecs.
    const codecSlashItems = wsSlug
      ? slashItemsFromRegistry({
          editor: editor as unknown as SlashContext['editor'],
          wsSlug,
          t,
          onError: (msg) => toast(msg, 'error'),
        })
      : []

    return (
      <div className="rounded border border-gray-200 bg-white" data-testid="markdown-editor">
        <BlockNoteView
          editor={editor}
          slashMenu={false}
          filePanel={wsSlug ? false : undefined}
          onChange={() => { if (settledRef.current) onDirtyRef.current() }}
        >
          {wsSlug && (
            <FilePanelController
              filePanel={(p) => <EditorFilePanel {...p} wsSlug={wsSlug} />}
            />
          )}
          {wsSlug && (
            <SuggestionMenuController
              triggerCharacter="/"
              getItems={async (query) =>
                filterItems(
                  [
                    linkSlashItem,
                    ...codecSlashItems,
                    ...getDefaultReactSlashMenuItems(editor),
                  ] as DefaultReactSuggestionItem[],
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

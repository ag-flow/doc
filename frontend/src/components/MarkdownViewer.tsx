import { useEffect, useRef } from 'react'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import '@blocknote/mantine/style.css'
import { docflowSchema, parseMarkdownWithCodecs, type CodecEditorApi } from '../lib/blockCodecs'
import { resolveArtifactUrl } from '../lib/artifacts'

interface MarkdownViewerProps {
  content: string
  /** Rendu sans cadre (bordure / fond) — pour la lecture prose « wiki ». */
  bare?: boolean
}

export function MarkdownViewer({ content, bare = false }: MarkdownViewerProps) {
  // Même schéma et même parsing que l'éditeur (registre de codecs) : le chemin
  // lecture (DocumentReader, PublicDocumentViewer) est couvert par transitivité.
  const editor = useCreateBlockNote({ schema: docflowSchema, resolveFileUrl: resolveArtifactUrl })
  const loadedRef = useRef(false)

  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    let cancelled = false
    void (async () => {
      const api = editor as unknown as CodecEditorApi
      const blocks = await parseMarkdownWithCodecs(api, content ?? '')
      if (cancelled) return
      if (blocks.length > 0) {
        editor.replaceBlocks(editor.document, blocks as never)
      }
    })()
    return () => { cancelled = true }
  }, [editor, content])

  return (
    <div className={bare ? 'wiki-prose' : 'rounded border border-gray-100 bg-white'}>
      <BlockNoteView editor={editor} editable={false} />
    </div>
  )
}

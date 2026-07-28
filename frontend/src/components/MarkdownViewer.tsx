import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import '@blocknote/mantine/style.css'
import { docflowSchema, parseMarkdownWithCodecs, type CodecEditorApi } from '../lib/blockCodecs'
import { resolveArtifactUrl } from '../lib/artifacts'
import { referencesApi } from '../lib/api'

interface MarkdownViewerProps {
  content: string
  /** Rendu sans cadre (bordure / fond) — pour la lecture prose « wiki ». */
  bare?: boolean
}

const DOC_LINK = /^docflow:\/\/doc\/([0-9a-fA-F-]{36})$/

export function MarkdownViewer({ content, bare = false }: MarkdownViewerProps) {
  const navigate = useNavigate()
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

  // Les liens internes docflow://doc/{id} ne sont pas des URLs navigables par
  // le navigateur : on les résout (workspace/bloc) puis on route dans l'app.
  // Non résolu (inconnu, non autorisé, lecteur public) : aucune navigation.
  function onClickCapture(e: React.MouseEvent) {
    const a = (e.target as HTMLElement).closest?.('a')
    if (!a) return
    const m = DOC_LINK.exec(a.getAttribute('href') ?? '')
    if (!m) return
    e.preventDefault()
    e.stopPropagation()
    void referencesApi
      .locate(m[1])
      .then((loc) => {
        if (!loc.block_slug) return
        void navigate(`/ws/${loc.workspace_slug}/blocs/${loc.block_slug}/documents/${loc.id}`)
      })
      .catch(() => undefined)
  }

  return (
    <div
      className={bare ? 'wiki-prose' : 'rounded border border-gray-100 bg-white'}
      onClickCapture={onClickCapture}
    >
      <BlockNoteView editor={editor} editable={false} />
    </div>
  )
}

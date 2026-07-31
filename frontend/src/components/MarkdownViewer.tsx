import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import '@blocknote/mantine/style.css'
import { docflowSchema, parseMarkdownWithCodecs, type CodecEditorApi } from '../lib/blockCodecs'
import { resolveArtifactUrl } from '../lib/artifacts'
import { referencesApi, artifactsApi } from '../lib/api'
import { useWorkspaceSlugOrNull } from '../contexts/WorkspaceContext'

interface MarkdownViewerProps {
  content: string
  /** Rendu sans cadre (bordure / fond) — pour la lecture prose « wiki ». */
  bare?: boolean
}

const DOC_LINK = /^docflow:\/\/doc\/([0-9a-fA-F-]{36})$/
const ARTIFACT_LINK = /^artifact:\/\/([0-9a-fA-F-]{36})$/

export function MarkdownViewer({ content, bare = false }: MarkdownViewerProps) {
  const navigate = useNavigate()
  const wsSlug = useWorkspaceSlugOrNull()
  // Même schéma et même parsing que l'éditeur (registre de codecs) : le chemin
  // lecture (DocumentReader, PublicDocumentViewer) est couvert par transitivité.
  const editor = useCreateBlockNote({ schema: docflowSchema, resolveFileUrl: resolveArtifactUrl })
  // Dernier contenu parsé : naviguer entre documents SANS remonter le
  // composant (sommaire, Précédent/Suivant, doc déjà en cache) doit re-parser
  // — un simple « déjà chargé » laissait l'article figé sur le premier doc.
  const lastParsedRef = useRef<string | null>(null)

  useEffect(() => {
    const next = content ?? ''
    if (lastParsedRef.current === next) return
    lastParsedRef.current = next
    let cancelled = false
    void (async () => {
      const api = editor as unknown as CodecEditorApi
      const blocks = await parseMarkdownWithCodecs(api, next)
      // Une navigation plus récente a relancé un parse : ne pas écraser.
      if (cancelled || lastParsedRef.current !== next) return
      if (blocks.length > 0) {
        editor.replaceBlocks(editor.document, blocks as never)
      } else {
        editor.replaceBlocks(editor.document, [{ type: 'paragraph' }] as never)
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
    const href = a.getAttribute('href') ?? ''

    // Lien artefact au fil du texte (une puce a son propre codec) : ouvrir dans
    // un nouvel onglet via un lien signé de courte durée.
    const art = ARTIFACT_LINK.exec(href)
    if (art) {
      e.preventDefault()
      e.stopPropagation()
      if (!wsSlug) return
      void artifactsApi
        .getLink(wsSlug, art[1])
        .then((link) => window.open(link.url, '_blank', 'noopener'))
        .catch(() => undefined)
      return
    }

    const m = DOC_LINK.exec(href)
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

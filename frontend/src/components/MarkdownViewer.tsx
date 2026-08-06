import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import '@blocknote/mantine/style.css'
import { docflowSchema, parseMarkdownWithCodecs, type CodecEditorApi } from '../lib/blockCodecs'
import { resolveArtifactUrl } from '../lib/artifacts'
import { referencesApi, artifactsApi } from '../lib/api'
import { useWorkspaceSlugOrNull } from '../contexts/WorkspaceContext'
import {
  documentToRichHtml,
  writeRichClipboard,
  type RichCopyEditor,
} from '../lib/richClipboard'

interface MarkdownViewerProps {
  content: string
  /** Rendu sans cadre (bordure / fond) — pour la lecture prose « wiki ». */
  bare?: boolean
}

/** Handle impératif : copie riche (texte HTML + composants en images). */
export interface MarkdownViewerHandle {
  copyRich: () => Promise<void>
}

const DOC_LINK = /^docflow:\/\/doc\/([0-9a-fA-F-]{36})$/
const UUID = '[0-9a-fA-F-]{36}'
// Schéma df : artifact://<uuid> (le workspace est celui du contexte courant).
const ARTIFACT_SCHEME = new RegExp(`^artifact://(${UUID})$`)
// URL brute d'artefact telle qu'insérée historiquement (upload / agent) :
// /api/workspaces/<ws>/artifacts/<uuid>, éventuellement absolue. On EXCLUT les
// sous-chemins signés (/download) et métadonnées (/meta) — seule l'URL nue est
// interceptée (le reste porte déjà sa propre authentification).
const ARTIFACT_RAW = new RegExp(`/api/workspaces/([^/\\s]+)/artifacts/(${UUID})(?:$|[?#])`)

/** Résout un href d'artefact (schéma df OU URL brute) en {ws, id}, sinon null.
 *  Exporté pour test. `currentWs` sert au schéma artifact:// (sans workspace). */
export function matchArtifactHref(
  href: string,
  currentWs: string | null,
): { ws: string; id: string } | null {
  const scheme = ARTIFACT_SCHEME.exec(href)
  if (scheme) return currentWs ? { ws: currentWs, id: scheme[1] } : null
  const raw = ARTIFACT_RAW.exec(href)
  if (raw) return { ws: raw[1], id: raw[2] }
  return null
}

export const MarkdownViewer = forwardRef<MarkdownViewerHandle, MarkdownViewerProps>(
  function MarkdownViewer({ content, bare = false }, ref) {
  const navigate = useNavigate()
  const wsSlug = useWorkspaceSlugOrNull()
  const rootRef = useRef<HTMLDivElement>(null)
  // Même schéma et même parsing que l'éditeur (registre de codecs) : le chemin
  // lecture (DocumentReader, PublicDocumentViewer) est couvert par transitivité.
  const editor = useCreateBlockNote({ schema: docflowSchema, resolveFileUrl: resolveArtifactUrl })

  // Copie riche : le DocumentReader déclenche cette action via le ref. Le HTML
  // sémantique du texte + les images rasterisées des composants graphiques sont
  // écrits dans le presse-papier (repli plein texte = le markdown source).
  useImperativeHandle(
    ref,
    () => ({
      async copyRich() {
        if (!rootRef.current) return
        const html = await documentToRichHtml(editor as unknown as RichCopyEditor, rootRef.current)
        await writeRichClipboard(html, content ?? '')
      },
    }),
    [editor, content],
  )
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

    // Lien artefact (schéma artifact:// OU URL brute /api/.../artifacts/{id}) :
    // le navigateur naviguerait sans Bearer → « token manquant ». On intercepte
    // et on ouvre un lien signé de courte durée dans un nouvel onglet.
    const art = matchArtifactHref(href, wsSlug)
    if (art) {
      e.preventDefault()
      e.stopPropagation()
      void artifactsApi
        .getLink(art.ws, art.id)
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
      ref={rootRef}
      className={bare ? 'wiki-prose' : 'rounded border border-gray-100 bg-white'}
      onClickCapture={onClickCapture}
    >
      <BlockNoteView editor={editor} editable={false} />
    </div>
  )
})

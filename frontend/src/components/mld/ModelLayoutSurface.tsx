/**
 * Surface d'affichage du type de contenu `model-layout` (épic MLD — F7).
 *
 * C'est ici que l'épic se rejoint : le registre de surfaces (F4) choisit ce
 * composant d'après `document.type`, l'adaptateur (F7) traduit les entités en
 * document de canvas, et le canvas générique (F6) les dessine.
 *
 * Le contrat est celui de n'importe quelle surface : la coquille de page ne sait
 * pas qu'elle affiche un diagramme, elle sait seulement sauvegarder ce que
 * `getContent()` lui rend.
 *
 * Les **entités** sont les documents ENFANTS de type `table-schema` — parce que
 * l'appartenance au modèle est l'arborescence, et non le corps de ce document,
 * qui ne porte que la mise en page.
 */

import { forwardRef, useCallback, useImperativeHandle, useMemo, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { parse as parseYaml, stringify as stringifyYaml } from 'yaml'
import { Canvas, type CanvasDoc } from '../../lib/canvas'
import { toCanvas, toLayout, type Entity, type ModelLayout } from '../../lib/mld/adapter'
import type {
  ContentEditorHandle,
  ContentEditorProps,
  ContentViewerHandle,
  ContentViewerProps,
} from '../../lib/contentSurfaces'
import { docsApi, type DocumentOut } from '../../lib/api'
import { useWorkspaceSlugOrNull } from '../../contexts/WorkspaceContext'

/** YAML illisible → objet vide : un contenu abîmé ne doit pas casser la page. */
function safeParse<T>(raw: string | null | undefined, fallback: T): T {
  if (!raw?.trim()) return fallback
  try {
    return (parseYaml(raw) as T) ?? fallback
  } catch {
    return fallback
  }
}

/**
 * État du diagramme : entités chargées depuis l'arborescence, mise en page lue
 * dans le corps, document de canvas courant.
 */
function useModelCanvas(content: string, docId: string | undefined) {
  const wsSlug = useWorkspaceSlugOrNull()

  // `listDocuments` rend des TÊTES de document : `content` y est toujours null.
  // Elle ne sert donc qu'à savoir QUI sont les entités de ce modèle ; leur corps
  // se récupère document par document.
  const { data: heads, isLoading: listing } = useQuery<DocumentOut[]>({
    queryKey: ['mld-entity-heads', wsSlug, docId],
    queryFn: () => docsApi.listDocuments(wsSlug as string),
    enabled: Boolean(wsSlug && docId),
    staleTime: 30_000,
  })

  const childIds = useMemo(
    () =>
      (heads ?? [])
        .filter((d) => d.parent_id === docId && d.type === 'table-schema')
        .map((d) => d.doc_technical_key),
    [heads, docId],
  )

  // Un aller-retour par entité, en parallèle et mis en cache par react-query.
  // Acceptable à l'échelle d'un modèle ; à remplacer par un point d'entrée qui
  // rend les enfants AVEC leur corps si les modèles deviennent gros.
  const bodies = useQueries({
    queries: childIds.map((id) => ({
      queryKey: ['document', wsSlug, id],
      queryFn: () => docsApi.getDocument(wsSlug as string, id),
      staleTime: 30_000,
    })),
  })

  const entities = useMemo<Entity[]>(
    () =>
      bodies
        .map((q) => q.data)
        .filter((d): d is DocumentOut => Boolean(d))
        .map((d) => ({ docId: d.doc_technical_key, schema: safeParse(d.content, {}) })),
    [bodies],
  )

  const isLoading = listing || bodies.some((q) => q.isLoading)

  const initial = useMemo(
    () => toCanvas(entities, safeParse<ModelLayout>(content, {})),
    [entities, content],
  )

  // `null` tant que l'utilisateur n'a rien bougé : c'est ce qui permet de rendre
  // le contenu d'origine intact à la sauvegarde, sans diff gratuit.
  const [edited, setEdited] = useState<CanvasDoc | null>(null)

  return { entities, isLoading, doc: edited ?? initial, edited, setEdited }
}

interface DiagramProps {
  doc: CanvasDoc
  onChange?: (doc: CanvasDoc) => void
  empty: boolean
  loading?: boolean
  readOnly?: boolean
}

function Diagram({ doc, onChange, empty, loading, readOnly }: DiagramProps) {
  const { t } = useTranslation()

  // Pendant le chargement des entités, ne PAS annoncer un modèle vide : le
  // message clignoterait à chaque ouverture.
  if (loading) {
    return <div data-testid="mld-loading" className="h-[70vh] w-full animate-pulse rounded bg-gray-50" />
  }
  if (empty) {
    return (
      <div
        data-testid="mld-empty"
        className="rounded border border-gray-200 bg-white p-6 text-sm text-gray-600"
      >
        {t('mld.noEntities')}
      </div>
    )
  }
  return (
    <div data-testid="mld-surface">
      <Canvas doc={doc} onChange={onChange} readOnly={readOnly} />
    </div>
  )
}

/** Surface d'ÉDITION — rend la mise en page courante à la sauvegarde. */
export const ModelLayoutEditor = forwardRef<ContentEditorHandle, ContentEditorProps>(
  ({ initialContent, onDirty, docId }, ref) => {
    const { entities, isLoading, doc, edited, setEdited } = useModelCanvas(initialContent, docId)

    useImperativeHandle(
      ref,
      () => ({
        getContent: async () =>
          // Rien n'a bougé → on rend le contenu d'origine TEL QUEL. Le
          // re-sérialiser produirait un diff sans changement de sens.
          edited ? stringifyYaml(toLayout(edited)) : initialContent,
      }),
      [edited, initialContent],
    )

    const handleChange = useCallback(
      (next: CanvasDoc) => {
        setEdited(next)
        onDirty()
      },
      [onDirty, setEdited],
    )

    return (
      <Diagram
        doc={doc}
        onChange={handleChange}
        empty={entities.length === 0}
        loading={isLoading}
      />
    )
  },
)
ModelLayoutEditor.displayName = 'ModelLayoutEditor'

/** Surface de LECTURE — même rendu, non modifiable. */
export const ModelLayoutViewer = forwardRef<ContentViewerHandle, ContentViewerProps>(
  ({ content, docId }, ref) => {
    const { entities, isLoading, doc } = useModelCanvas(content, docId)
    // Pas de copie riche : un diagramme n'a pas de représentation HTML fidèle.
    useImperativeHandle(ref, () => ({}), [])

    return <Diagram doc={doc} empty={entities.length === 0} loading={isLoading} readOnly />
  },
)
ModelLayoutViewer.displayName = 'ModelLayoutViewer'

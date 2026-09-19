/**
 * Surface du type de contenu `model-layout` — diagramme de modèle de données.
 *
 * **Chargée à la demande.** Le moteur de rendu du canvas pèse ~240 ko : un
 * utilisateur qui ne lit que du markdown n'a pas à le télécharger. Le registre
 * doit pourtant connaître la surface dès le départ, pour savoir qu'elle existe —
 * d'où ces enveloppes, qui déclarent la surface sans embarquer son code.
 *
 * (elkjs, plus lourd encore, est déjà différé une seconde fois : il n'arrive
 * qu'au premier ré-arrangement — cf. `lib/canvas/layout.ts`.)
 */

import { forwardRef, lazy, Suspense } from 'react'
import type {
  ContentEditorHandle,
  ContentEditorProps,
  ContentSurface,
  ContentViewerHandle,
  ContentViewerProps,
} from './index'

export const MODEL_LAYOUT_CONTENT_TYPE = 'model-layout'

const LazyEditor = lazy(() =>
  import('../../components/mld/ModelLayoutSurface').then((m) => ({ default: m.ModelLayoutEditor })),
)
const LazyViewer = lazy(() =>
  import('../../components/mld/ModelLayoutSurface').then((m) => ({ default: m.ModelLayoutViewer })),
)

/** Réservation de place pendant le chargement — évite un saut de mise en page. */
function Loading() {
  return <div className="h-[70vh] w-full animate-pulse rounded bg-gray-50" aria-busy="true" />
}

const Editor = forwardRef<ContentEditorHandle, ContentEditorProps>((props, ref) => (
  <Suspense fallback={<Loading />}>
    <LazyEditor {...props} ref={ref} />
  </Suspense>
))
Editor.displayName = 'ModelLayoutEditorLazy'

const Viewer = forwardRef<ContentViewerHandle, ContentViewerProps>((props, ref) => (
  <Suspense fallback={<Loading />}>
    <LazyViewer {...props} ref={ref} />
  </Suspense>
))
Viewer.displayName = 'ModelLayoutViewerLazy'

export const modelLayoutSurface: ContentSurface = {
  contentType: MODEL_LAYOUT_CONTENT_TYPE,
  Editor,
  Viewer,
  // Un diagramme n'a pas de représentation HTML fidèle à mettre au presse-papiers.
  supportsRichCopy: false,
}

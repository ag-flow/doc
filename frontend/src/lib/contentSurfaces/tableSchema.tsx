/**
 * Surface du type de contenu `table-schema` — édition d'une entité.
 *
 * Chargée à la demande, comme la surface de diagramme : le code d'édition d'une
 * entité n'a pas à peser sur le chargement d'une page markdown.
 */

import { forwardRef, lazy, Suspense } from 'react'
import type {
  ContentEditorHandle,
  ContentEditorProps,
  ContentSurface,
  ContentViewerHandle,
  ContentViewerProps,
} from './index'

export const TABLE_SCHEMA_CONTENT_TYPE = 'table-schema'

const LazyEditor = lazy(() =>
  import('../../components/mld/TableSchemaSurface').then((m) => ({ default: m.TableSchemaEditor })),
)
const LazyViewer = lazy(() =>
  import('../../components/mld/TableSchemaSurface').then((m) => ({ default: m.TableSchemaViewer })),
)

function Loading() {
  return <div className="h-64 w-full animate-pulse rounded bg-gray-50" aria-busy="true" />
}

const Editor = forwardRef<ContentEditorHandle, ContentEditorProps>((props, ref) => (
  <Suspense fallback={<Loading />}>
    <LazyEditor {...props} ref={ref} />
  </Suspense>
))
Editor.displayName = 'TableSchemaEditorLazy'

const Viewer = forwardRef<ContentViewerHandle, ContentViewerProps>((props, ref) => (
  <Suspense fallback={<Loading />}>
    <LazyViewer {...props} ref={ref} />
  </Suspense>
))
Viewer.displayName = 'TableSchemaViewerLazy'

export const tableSchemaSurface: ContentSurface = {
  contentType: TABLE_SCHEMA_CONTENT_TYPE,
  labelKey: 'contentType.tableSchema',
  Editor,
  Viewer,
  supportsRichCopy: false,
  fullWidth: true,
}

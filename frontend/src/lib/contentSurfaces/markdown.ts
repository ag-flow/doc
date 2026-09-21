/** Surface du type de contenu `md` — BlockNote. */

import { MarkdownEditor } from '../../components/MarkdownEditor'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import type { ContentSurface } from './index'

/** Valeur historique de `document.type` (défaut DDL, cf. `docflow.documents.content_types`). */
export const MARKDOWN_CONTENT_TYPE = 'md'

export const markdownSurface: ContentSurface = {
  contentType: MARKDOWN_CONTENT_TYPE,
  labelKey: 'contentType.markdown',
  Editor: MarkdownEditor,
  Viewer: MarkdownViewer,
  supportsRichCopy: true,
}

/** Surface du type de contenu `md` — BlockNote. */

import { MarkdownEditor } from '../../components/MarkdownEditor'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import type { ContentSurface } from './index'
import type { FlowBlock, PrintLayout } from '../print/layout'

/** Valeur historique de `document.type` (défaut DDL, cf. `docflow.documents.content_types`). */
export const MARKDOWN_CONTENT_TYPE = 'md'

/** Types de blocs BlockNote sécables — une coupure peut tomber dedans. */
const BREAKABLE_CT = new Set(['paragraph', 'bulletListItem', 'numberedListItem', 'checkListItem'])

/**
 * Blocs de flux du rendu BlockNote.
 *
 * **C'est le seul endroit du produit qui connaît la structure DOM de BlockNote.**
 * Cette fonction vivait dans la page d'impression, qui supposait donc que tout
 * document était du markdown : une surface non-markdown n'y trouvait aucun bloc.
 * Elle appartient à la surface qui produit ce DOM.
 *
 * Attention au vocabulaire : `data-content-type` est ici l'attribut de BlockNote
 * (son type de bloc), à ne pas confondre avec `document.type` ni avec l'attribut
 * de même nom que pose notre propre `BlockFrame`.
 */
function markdownFlowBlocks(root: HTMLElement): FlowBlock[] {
  const rootTop = root.getBoundingClientRect().top
  const nodes: HTMLElement[] = []
  root.querySelectorAll<HTMLElement>(':scope > h1').forEach((h) => nodes.push(h))
  Array.from(root.querySelectorAll<HTMLElement>('.bn-block-outer'))
    .filter((b) => !b.parentElement?.closest('.bn-block-outer'))
    .forEach((b) => nodes.push(b))

  return nodes
    .map((el) => {
      const r = el.getBoundingClientRect()
      const top = r.top - rootTop
      const ct = el.matches('h1,h2,h3,h4,h5,h6')
        ? 'heading'
        : (el.querySelector('.bn-block-content')?.getAttribute('data-content-type') ?? '')
      const kind: FlowBlock['kind'] =
        ct === 'heading' ? 'heading' : BREAKABLE_CT.has(ct) ? 'break' : 'component'
      return { top, bottom: top + r.height, kind }
    })
    .sort((a, b) => a.top - b.top)
}

export const markdownSurface: ContentSurface = {
  contentType: MARKDOWN_CONTENT_TYPE,
  labelKey: 'contentType.markdown',
  Editor: MarkdownEditor,
  Viewer: MarkdownViewer,
  supportsRichCopy: true,
  getPrintLayout: (root): PrintLayout => ({ mode: 'flow', blocks: markdownFlowBlocks(root) }),
}

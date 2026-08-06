/**
 * Copie « riche » d'un document rendu : le texte devient du HTML sémantique
 * (titres, listes, tableaux, liens, gras…) et chaque composant graphique
 * (df-timeline, df-chart, df-conversation, df-display, mermaid, dataset) est
 * rasterisé en image PNG. Cible : coller dans Confluence ou un autre éditeur
 * riche en gardant la mise en forme ET le visuel des composants.
 */
import { domToPng } from 'modern-screenshot'

/** Types de blocs BlockNote rendus comme composants graphiques → image. */
export const GRAPHICAL_BLOCK_TYPES = new Set([
  'dfChart',
  'dfTimeline',
  'dfConversation',
  'dfDisplay',
  'mermaid',
  'dataset',
])

/** Sous-ensemble de l'API BlockNote nécessaire à la copie riche. */
export interface RichCopyEditor {
  document: Array<{ id: string; type: string }>
  blocksToHTMLLossy: (blocks: unknown[]) => Promise<string>
}

/** Rasterise un nœud DOM en data-URL PNG. Injectable pour les tests. */
export type Rasterize = (node: HTMLElement) => Promise<string>

const defaultRasterize: Rasterize = (node) =>
  domToPng(node, { scale: 2, backgroundColor: '#ffffff' })

function cssEscape(value: string): string {
  // CSS.escape existe dans les navigateurs modernes et jsdom ; repli défensif.
  return typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(value) : value.replace(/"/g, '\\"')
}

/**
 * Construit le HTML riche du document : runs de texte consécutifs exportés via
 * l'exporteur BlockNote (HTML propre), composants graphiques remplacés par une
 * image PNG rasterisée depuis leur rendu DOM réel. Un composant dont le nœud
 * DOM est introuvable retombe sur l'export texte (jamais d'image vide).
 */
export async function documentToRichHtml(
  editor: RichCopyEditor,
  container: HTMLElement,
  rasterize: Rasterize = defaultRasterize,
): Promise<string> {
  const parts: string[] = []
  let run: unknown[] = []
  const flushRun = async () => {
    if (run.length) {
      parts.push(await editor.blocksToHTMLLossy(run))
      run = []
    }
  }

  for (const block of editor.document) {
    const node = GRAPHICAL_BLOCK_TYPES.has(block.type)
      ? container.querySelector<HTMLElement>(`[data-id="${cssEscape(block.id)}"] .bn-block-content`)
      : null
    if (node) {
      await flushRun()
      const png = await rasterize(node)
      parts.push(`<p><img src="${png}" alt="${block.type}" style="max-width:100%" /></p>`)
    } else {
      run.push(block)
    }
  }
  await flushRun()
  return `<div>${parts.join('\n')}</div>`
}

/**
 * Écrit le presse-papier en `text/html` (mise en forme + images) avec un repli
 * `text/plain`. Si l'API riche n'est pas disponible, écrit le texte seul.
 */
export async function writeRichClipboard(html: string, plain: string): Promise<void> {
  const canWriteRich =
    typeof ClipboardItem !== 'undefined' && typeof navigator.clipboard?.write === 'function'
  if (!canWriteRich) {
    await navigator.clipboard?.writeText(plain)
    return
  }
  await navigator.clipboard.write([
    new ClipboardItem({
      'text/html': new Blob([html], { type: 'text/html' }),
      'text/plain': new Blob([plain], { type: 'text/plain' }),
    }),
  ])
}

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

/**
 * Construit le HTML riche du document : les runs de texte consécutifs sont
 * exportés via l'exporteur BlockNote (HTML propre), et chaque composant
 * graphique est remplacé par une image PNG rasterisée depuis son cadre rendu.
 *
 * Les cadres graphiques sont repérés par le marqueur explicite `data-df-component`
 * posé par `BlockFrame` (indépendant des classes internes de BlockNote) et
 * appariés aux blocs graphiques du document DANS L'ORDRE — chaque bloc graphique
 * rend exactement un cadre. Un composant n'est JAMAIS perdu : si la rasterisation
 * échoue (image cross-origin taintée…), on retombe sur son HTML rendu.
 */
export async function documentToRichHtml(
  editor: RichCopyEditor,
  container: HTMLElement,
  rasterize: Rasterize = defaultRasterize,
): Promise<string> {
  const componentNodes = Array.from(
    container.querySelectorAll<HTMLElement>('[data-df-component]'),
  )
  let componentIndex = 0

  const parts: string[] = []
  let run: unknown[] = []
  const flushRun = async () => {
    if (run.length) {
      parts.push(await editor.blocksToHTMLLossy(run))
      run = []
    }
  }

  for (const block of editor.document) {
    if (!GRAPHICAL_BLOCK_TYPES.has(block.type)) {
      run.push(block)
      continue
    }
    await flushRun()
    const node = componentNodes[componentIndex++]
    if (!node) continue // pas de cadre rendu (rare) : rien à rasteriser
    try {
      const png = await rasterize(node)
      parts.push(`<p><img src="${png}" alt="${block.type}" style="max-width:100%" /></p>`)
    } catch {
      // Rasterisation impossible → conserver le rendu HTML du composant plutôt
      // que de le perdre silencieusement.
      parts.push(`<div>${node.innerHTML}</div>`)
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

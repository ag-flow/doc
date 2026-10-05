import { describe, it, expect, vi } from 'vitest'
import {
  documentToRichHtml,
  writeRichClipboard,
  GRAPHICAL_BLOCK_TYPES,
  type RichCopyEditor,
} from '../lib/richClipboard'

/** Éditeur factice : document plat + export texte concaténant les ids. */
function fakeEditor(blocks: Array<{ id: string; type: string }>): RichCopyEditor {
  return {
    document: blocks,
    blocksToHTMLLossy: vi.fn(async (bs: unknown[]) => {
      const ids = (bs as Array<{ id: string }>).map((b) => b.id)
      return `<p>${ids.join(',')}</p>`
    }),
  }
}

/** Conteneur DOM avec un cadre [data-df-component] par composant graphique,
 *  dans l'ordre du document (le marqueur posé par BlockFrame). */
function container(typeLabels: string[]): HTMLElement {
  const root = document.createElement('div')
  for (const label of typeLabels) {
    const frame = document.createElement('div')
    frame.setAttribute('data-df-component', label)
    frame.innerHTML = `<span>rendu-${label}</span>`
    root.appendChild(frame)
  }
  return root
}

describe('documentToRichHtml', () => {
  it('rasterise les composants graphiques et exporte le texte par runs', async () => {
    const blocks = [
      { id: 'p1', type: 'paragraph' },
      { id: 'h1', type: 'heading' },
      { id: 'c1', type: 'dfChart' },
      { id: 'p2', type: 'paragraph' },
      { id: 'm1', type: 'mermaid' },
    ]
    const rasterize = vi.fn(
      async (node: HTMLElement) => `data:image/png;base64,${node.getAttribute('data-df-component')}`,
    )

    // Deux cadres graphiques dans l'ordre du document : chart puis mermaid.
    const html = await documentToRichHtml(fakeEditor(blocks), container(['chart', 'mermaid']), rasterize)

    // Deux composants rasterisés (chart + mermaid), deux images produites.
    expect(rasterize).toHaveBeenCalledTimes(2)
    // Runs de texte consécutifs regroupés : [p1,h1] puis [p2] — pas un export par bloc.
    expect(html).toContain('<p>p1,h1</p>')
    expect(html).toContain('<p>p2</p>')
    // Ordre du document préservé : texte, image chart, texte, image mermaid.
    expect(html.indexOf('p1,h1')).toBeLessThan(html.indexOf('alt="dfChart"'))
    expect(html.indexOf('alt="dfChart"')).toBeLessThan(html.indexOf('p2'))
    expect(html.indexOf('p2')).toBeLessThan(html.indexOf('alt="mermaid"'))
    // Le bon cadre est apparié au bon bloc, dans l'ordre.
    expect(html).toContain('<img src="data:image/png;base64,chart"')
    expect(html).toContain('<img src="data:image/png;base64,mermaid"')
  })

  it('conserve le rendu HTML du composant si la rasterisation échoue', async () => {
    const blocks = [
      { id: 'p1', type: 'paragraph' },
      { id: 'd1', type: 'dfDisplay' },
    ]
    const rasterize = vi.fn(async () => {
      throw new Error('canvas taintée')
    })
    const html = await documentToRichHtml(fakeEditor(blocks), container(['display']), rasterize)
    // Jamais de perte : le rendu DOM du composant est conservé en repli.
    expect(html).toContain('rendu-display')
    expect(html).not.toContain('<img')
  })

  it('couvre les six types de composants graphiques', () => {
    expect([...GRAPHICAL_BLOCK_TYPES].sort()).toEqual(
      ['dataset', 'dfChart', 'dfConversation', 'dfDisplay', 'dfTimeline', 'mermaid'].sort(),
    )
  })
})

describe('writeRichClipboard', () => {
  it('écrit text/html + text/plain quand ClipboardItem est disponible', async () => {
    const write = vi.fn(async (..._args: unknown[]) => undefined)
    class FakeClipboardItem {
      items: Record<string, Blob>
      constructor(items: Record<string, Blob>) {
        this.items = items
      }
    }
    vi.stubGlobal('ClipboardItem', FakeClipboardItem)
    vi.stubGlobal('navigator', { clipboard: { write, writeText: vi.fn() } })

    await writeRichClipboard('<div>x</div>', 'x')

    expect(write).toHaveBeenCalledOnce()
    // write([ new ClipboardItem({...}) ]) → 1er arg = tableau d'un ClipboardItem.
    const arg = write.mock.calls[0][0] as Array<{ items: Record<string, Blob> }>
    expect(Object.keys(arg[0].items)).toEqual(['text/html', 'text/plain'])
    vi.unstubAllGlobals()
  })

  it('repli plein texte si l’API riche est absente', async () => {
    const writeText = vi.fn(async () => undefined)
    vi.stubGlobal('ClipboardItem', undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    await writeRichClipboard('<div>x</div>', 'plain-fallback')

    expect(writeText).toHaveBeenCalledWith('plain-fallback')
    vi.unstubAllGlobals()
  })
})

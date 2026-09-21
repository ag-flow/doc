/** Enveloppe d'un document de canvas — étendue réelle pour l'impression (F4d). */

import { describe, it, expect } from 'vitest'
import { contentBounds, LABEL_MARGIN } from '../lib/canvas/bounds'
import { emptyCanvas, type CanvasDoc, type CanvasNode } from '../lib/canvas/model'

function node(id: string, x: number, y: number, w = 200, h = 100): CanvasNode {
  return { id, kind: 'entite', position: { x, y }, size: { width: w, height: h } }
}

function doc(over: Partial<CanvasDoc> = {}): CanvasDoc {
  return { schemaVersion: 1, nodes: [], edges: [], ...over }
}

describe('contentBounds', () => {
  it('englobe les boîtes, marge de textes comprise', () => {
    const b = contentBounds(doc({ nodes: [node('a', 0, 0), node('b', 400, 300)] }))

    // Contenu réel : (0,0) → (600,400). La marge l'élargit des deux côtés.
    expect(b.x).toBe(-LABEL_MARGIN)
    expect(b.y).toBe(-LABEL_MARGIN)
    expect(b.width).toBe(600 + 2 * LABEL_MARGIN)
    expect(b.height).toBe(400 + 2 * LABEL_MARGIN)
  })

  it('couvre un coude qui SORT de l\'enveloppe des nœuds', () => {
    // Un lien peut être routé bien au-delà des boîtes qu'il relie : l'oublier
    // couperait le tracé au milieu, sans un mot.
    const b = contentBounds(
      doc({
        nodes: [node('a', 0, 0)],
        edges: [
          {
            id: 'r1',
            source: { node: 'a' },
            target: { node: 'a' },
            waypoints: [{ x: 900, y: 700 }],
          },
        ],
      }),
    )

    expect(b.width).toBe(900 + 2 * LABEL_MARGIN)
    expect(b.height).toBe(700 + 2 * LABEL_MARGIN)
  })

  it('rend des coordonnées NÉGATIVES quand le contenu précède l\'origine', () => {
    // Rien n'oblige un diagramme à commencer en (0,0) : l'appelant translate.
    const b = contentBounds(doc({ nodes: [node('a', -500, -200)] }))

    expect(b.x).toBe(-500 - LABEL_MARGIN)
    expect(b.y).toBe(-200 - LABEL_MARGIN)
  })

  it('retombe sur une taille par défaut quand le nœud n\'en déclare pas', () => {
    const sansTaille: CanvasNode = { id: 'a', kind: 'entite', position: { x: 0, y: 0 } }
    const b = contentBounds(doc({ nodes: [sansTaille] }))

    // `nodeSize` fournit le défaut : l'enveloppe n'est jamais dégénérée.
    expect(b.width).toBeGreaterThan(2 * LABEL_MARGIN)
    expect(b.height).toBeGreaterThan(2 * LABEL_MARGIN)
  })

  it('un document sans nœud n\'a pas d\'étendue', () => {
    // Zéro, pas une marge autour de rien : il n'y a rien à imprimer.
    expect(contentBounds(emptyCanvas())).toEqual({ x: 0, y: 0, width: 0, height: 0 })
  })
})

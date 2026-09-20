/** Cœur algorithmique du canvas : ancrage, routage, paliers (épic MLD — F6). */

import { describe, it, expect } from 'vitest'
import { anchorPoint, sidesFor } from '../lib/canvas/anchor'
import {
  endMarkPoint,
  midpointOf,
  orthogonalRoute,
  simplify,
  toSvgPath,
  STUB,
} from '../lib/canvas/route'
import { detailFor, portsVisibleAt } from '../lib/canvas/detail'
import type { CanvasNode } from '../lib/canvas/model'

function node(id: string, x: number, y: number, extra: Partial<CanvasNode> = {}): CanvasNode {
  return {
    id,
    kind: 'table',
    position: { x, y },
    size: { width: 200, height: 100 },
    ports: [
      { id: 'f1', offset: 20 },
      { id: 'f2', offset: 60 },
    ],
    ...extra,
  }
}

// ── Choix du côté ─────────────────────────────────────────────────────────────

describe('sidesFor — côté d\'ancrage selon la position relative', () => {
  it('sort à droite et entre à gauche quand la cible est à droite (cas nominal)', () => {
    expect(sidesFor(node('a', 0, 0), node('b', 400, 0))).toEqual(['right', 'left'])
  })

  it('inverse quand la cible est à gauche, pour ne pas contourner sa propre boîte', () => {
    expect(sidesFor(node('a', 400, 0), node('b', 0, 0))).toEqual(['left', 'right'])
  })

  it('bascule en vertical quand l\'écart vertical domine', () => {
    expect(sidesFor(node('a', 0, 0), node('b', 20, 500))).toEqual(['bottom', 'top'])
    expect(sidesFor(node('a', 0, 500), node('b', 20, 0))).toEqual(['top', 'bottom'])
  })

  it('reste horizontal sur un simple décalage vertical', () => {
    // Sans axe dominant, le lien ne doit pas sauter d'un côté à l'autre.
    expect(sidesFor(node('a', 0, 0), node('b', 400, 40))).toEqual(['right', 'left'])
  })
})

// ── Ancrage sur le port ───────────────────────────────────────────────────────

describe('anchorPoint — ancrage fin', () => {
  it('accroche à la hauteur du port, sur le bord demandé', () => {
    const a = anchorPoint(node('a', 100, 50), 'f2', 'right')
    expect(a.degraded).toBe(false)
    expect(a.point).toEqual({ x: 300, y: 110 }) // 100+200 ; 50+60
  })

  it('accroche à gauche sans décaler en x', () => {
    expect(anchorPoint(node('a', 100, 50), 'f1', 'left').point).toEqual({ x: 100, y: 70 })
  })
})

describe('anchorPoint — dégradation vers le bord', () => {
  const n = node('a', 100, 50)

  it('dégrade quand aucun port n\'est demandé', () => {
    const a = anchorPoint(n, undefined, 'right')
    expect(a.degraded).toBe(true)
    expect(a.point).toEqual({ x: 300, y: 100 }) // milieu du côté
  })

  it('dégrade quand le port n\'existe plus', () => {
    // Le lien a survécu à la suppression du champ : il ne doit pas disparaître.
    expect(anchorPoint(n, 'champ-supprime', 'right').degraded).toBe(true)
  })

  it('dégrade quand le nœud est replié', () => {
    expect(anchorPoint(node('a', 100, 50, { collapsed: true }), 'f1', 'right').degraded).toBe(true)
  })

  it('dégrade quand le palier de zoom masque les ports', () => {
    expect(anchorPoint(n, 'f1', 'right', { portsVisible: false }).degraded).toBe(true)
  })

  it('dégrade sur les côtés haut/bas, où la hauteur d\'un port n\'a pas de sens', () => {
    expect(anchorPoint(n, 'f1', 'top').degraded).toBe(true)
    expect(anchorPoint(n, 'f1', 'bottom').point).toEqual({ x: 200, y: 150 })
  })

  it('borne l\'ancre à la boîte si l\'offset est périmé', () => {
    const grand = node('a', 0, 0, { ports: [{ id: 'f1', offset: 9999 }] })
    expect(anchorPoint(grand, 'f1', 'right').point.y).toBe(100) // hauteur du nœud
  })
})

// ── Routage orthogonal ────────────────────────────────────────────────────────

type P = { x: number; y: number }

const isOrthogonal = (pts: P[]) =>
  pts.every((p, i) => i === 0 || p.x === pts[i - 1].x || p.y === pts[i - 1].y)

/** Le tracé quitte/rejoint le bord perpendiculairement ?
 *  On vérifie la DIRECTION du premier (resp. dernier) segment, et non la
 *  présence d'un sommet : `simplify` fusionne les points alignés, ce qui
 *  supprime le sommet du moignon sans changer la forme du tracé. */
const segmentIsHorizontal = (a: P, b: P) => a.y === b.y && a.x !== b.x

/** Le point `p` est-il sur l'un des segments du tracé ? */
function passesThrough(pts: P[], p: P): boolean {
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1]
    const b = pts[i]
    const onVertical = a.x === b.x && p.x === a.x && p.y >= Math.min(a.y, b.y) && p.y <= Math.max(a.y, b.y)
    const onHorizontal = a.y === b.y && p.y === a.y && p.x >= Math.min(a.x, b.x) && p.x <= Math.max(a.x, b.x)
    if (onVertical || onHorizontal) return true
  }
  return false
}

describe('orthogonalRoute', () => {
  const src = { point: { x: 100, y: 50 }, side: 'right' as const, degraded: false }
  const dst = { point: { x: 400, y: 200 }, side: 'left' as const, degraded: false }

  it('ne produit que des segments horizontaux ou verticaux', () => {
    expect(isOrthogonal(orthogonalRoute(src, dst))).toBe(true)
  })

  it('part et arrive perpendiculairement au bord', () => {
    const pts = orthogonalRoute(src, dst)

    expect(pts[0]).toEqual({ x: 100, y: 50 })
    expect(pts[pts.length - 1]).toEqual({ x: 400, y: 200 })
    // Bords gauche/droite ⇒ premier et dernier segments horizontaux.
    expect(segmentIsHorizontal(pts[0], pts[1])).toBe(true)
    expect(segmentIsHorizontal(pts[pts.length - 2], pts[pts.length - 1])).toBe(true)
  })

  it('dégage la boîte d\'au moins un moignon avant de tourner', () => {
    const pts = orthogonalRoute(src, dst)
    // Le premier segment va vers la droite, et d'au moins STUB : sans quoi le
    // lien collerait au bord du nœud.
    expect(pts[1].x - pts[0].x).toBeGreaterThanOrEqual(STUB)
  })

  it('relie deux ancres alignées par une ligne droite', () => {
    const droit = orthogonalRoute(src, { point: { x: 400, y: 50 }, side: 'left', degraded: false })
    expect(droit).toEqual([
      { x: 100, y: 50 },
      { x: 400, y: 50 },
    ])
  })

  it('traverse les coudes imposés par l\'utilisateur, dans l\'ordre', () => {
    const impose = { x: 250, y: 400 }
    const pts = orthogonalRoute(src, dst, [impose])

    expect(isOrthogonal(pts)).toBe(true)
    // Le tracé PASSE par le coude ; il n'a pas à en faire un sommet distinct
    // (un coude aligné avec ses voisins est fusionné, la forme est identique).
    expect(passesThrough(pts, impose)).toBe(true)
  })

  it('n\'écrase pas une intention explicite par un recalcul', () => {
    const auto = orthogonalRoute(src, dst)
    const manuel = orthogonalRoute(src, dst, [{ x: 250, y: 400 }])
    expect(manuel).not.toEqual(auto)
  })

  it('gère des bords d\'axes différents', () => {
    const vertical = { point: { x: 400, y: 300 }, side: 'top' as const, degraded: false }
    expect(isOrthogonal(orthogonalRoute(src, vertical))).toBe(true)
  })
})

describe('simplify', () => {
  it('retire les doublons et les points alignés', () => {
    expect(
      simplify([
        { x: 0, y: 0 },
        { x: 0, y: 0 },
        { x: 5, y: 0 },
        { x: 10, y: 0 },
        { x: 10, y: 10 },
      ]),
    ).toEqual([
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
    ])
  })
})

describe('midpointOf — milieu VISUEL du tracé', () => {
  it('suit la longueur parcourue, pas le rang du point', () => {
    // Coudes serrés au départ : le point du milieu de la LISTE (30,0) serait
    // collé à la boîte source. Le milieu en longueur tombe à 50 sur 100.
    expect(
      midpointOf([
        { x: 0, y: 0 },
        { x: 10, y: 0 },
        { x: 30, y: 0 },
        { x: 100, y: 0 },
      ]),
    ).toEqual({ x: 50, y: 0 })
  })

  it('dégrade sans planter sur un tracé vide ou ponctuel', () => {
    expect(midpointOf([])).toEqual({ x: 0, y: 0 })
    expect(midpointOf([{ x: 7, y: 7 }])).toEqual({ x: 7, y: 7 })
  })
})

describe('endMarkPoint — multiplicité posée au bord', () => {
  it('se place du côté par lequel le lien quitte la boîte', () => {
    const at = { x: 100, y: 50 }
    expect(endMarkPoint(at, 'right').x).toBeGreaterThan(at.x)
    expect(endMarkPoint(at, 'left').x).toBeLessThan(at.x)
    expect(endMarkPoint(at, 'top').y).toBeLessThan(at.y)
    expect(endMarkPoint(at, 'bottom').y).toBeGreaterThan(at.y)
  })

  it('reste plus près du bord que le bout du moignon', () => {
    // C'est tout l'objet de la correction : au bout du moignon, la marque
    // flottait sans qu'on sache à quelle boîte la rattacher.
    const at = { x: 100, y: 50 }
    expect(endMarkPoint(at, 'right').x - at.x).toBeLessThan(STUB)
  })

  it('se décale de côté pour ne pas s\'asseoir sur le trait', () => {
    const at = { x: 100, y: 50 }
    expect(endMarkPoint(at, 'right').y).not.toBe(at.y)
    expect(endMarkPoint(at, 'top').x).not.toBe(at.x)
  })
})

describe('toSvgPath', () => {
  it('produit un tracé SVG à partir des points', () => {
    expect(
      toSvgPath([
        { x: 0, y: 0 },
        { x: 10, y: 0 },
      ]),
    ).toBe('M 0,0 L 10,0')
  })

  it('rend une chaîne vide sans points', () => {
    expect(toSvgPath([])).toBe('')
  })
})

// ── Paliers de détail ─────────────────────────────────────────────────────────

describe('detailFor', () => {
  it.each([
    [1.5, 'fields'],
    [0.75, 'fields'],
    [0.5, 'title'],
    [0.2, 'silhouette'],
  ] as const)('zoom %s → palier %s', (zoom, level) => {
    expect(detailFor(zoom)).toBe(level)
  })

  it('ne rend les ports accrochables que lorsque les champs sont dessinés', () => {
    // C'est ce qui relie le zoom à la dégradation de l'ancrage.
    expect(portsVisibleAt(1)).toBe(true)
    expect(portsVisibleAt(0.5)).toBe(false)
  })
})

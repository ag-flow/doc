import { describe, it, expect } from 'vitest'
import {
  linearScale,
  timeScale,
  niceTicks,
  extentOf,
  timeExtent,
  cartesianFrame,
  radialPoint,
  radialPoints,
  radialAngle,
  quadrantGrid,
  lanes,
} from '../lib/diagramLayout'

describe('linearScale', () => {
  it('projette les bornes et le milieu', () => {
    const s = linearScale([0, 10], [0, 100])
    expect(s(0)).toBe(0)
    expect(s(10)).toBe(100)
    expect(s(5)).toBe(50)
  })

  it('inverse la projection', () => {
    const s = linearScale([0, 10], [0, 200])
    expect(s.invert(100)).toBe(5)
    expect(s.invert(s(7))).toBeCloseTo(7)
  })

  it('domaine plat → milieu de la plage (pas de division par zéro)', () => {
    const s = linearScale([5, 5], [0, 100])
    expect(s(5)).toBe(50)
    expect(Number.isFinite(s(42))).toBe(true)
  })

  it('supporte une plage inversée (Y écran)', () => {
    const s = linearScale([0, 1], [100, 0])
    expect(s(0)).toBe(100)
    expect(s(1)).toBe(0)
  })
})

describe('niceTicks', () => {
  it('produit des crans ronds dans le domaine', () => {
    const t = niceTicks(0, 100, 5)
    expect(t[0]).toBe(0)
    expect(t[t.length - 1]).toBeLessThanOrEqual(100)
    // Pas rond de 20 pour ~5 crans : tous multiples du pas, bornes incluses.
    expect(t).toEqual([0, 20, 40, 60, 80, 100])
  })

  it('domaine ponctuel → une seule valeur', () => {
    expect(niceTicks(7, 7)).toEqual([7])
  })

  it('ne boucle pas et reste borné', () => {
    expect(niceTicks(0, 3, 5).length).toBeLessThanOrEqual(8)
  })
})

describe('extentOf / timeExtent', () => {
  it('ignore les NaN/Infini', () => {
    expect(extentOf([3, NaN, 1, Infinity, 8])).toEqual([1, 8])
  })
  it('série vide → [0, 0]', () => {
    expect(extentOf([])).toEqual([0, 0])
  })
  it('timeExtent convertit les Date en ms', () => {
    const a = new Date('2026-01-01T00:00:00Z')
    const b = new Date('2026-01-02T00:00:00Z')
    expect(timeExtent([b, a])).toEqual([a.getTime(), b.getTime()])
  })
})

describe('timeScale', () => {
  it('mappe un domaine de dates vers des pixels', () => {
    const a = new Date('2026-01-01T00:00:00Z')
    const b = new Date('2026-01-03T00:00:00Z')
    const mid = new Date('2026-01-02T00:00:00Z')
    const s = timeScale([a, b], [0, 200])
    expect(s(a.getTime())).toBe(0)
    expect(s(b.getTime())).toBe(200)
    expect(s(mid.getTime())).toBeCloseTo(100)
  })
})

describe('cartesianFrame', () => {
  it("réserve l'aire de tracé selon le padding", () => {
    const f = cartesianFrame({ width: 120, height: 100, padding: 10 })
    expect(f.plot).toEqual({ x: 10, y: 10, width: 100, height: 80 })
  })

  it('inverse Y (min en bas, max en haut de l’écran)', () => {
    const f = cartesianFrame({ width: 100, height: 100, padding: 0, yDomain: [0, 10] })
    expect(f.y(0)).toBe(100) // bas
    expect(f.y(10)).toBe(0) // haut
  })

  it('projette un point de données', () => {
    const f = cartesianFrame({
      width: 100,
      height: 100,
      padding: 0,
      xDomain: [0, 10],
      yDomain: [0, 10],
    })
    expect(f.project({ x: 5, y: 5 })).toEqual({ x: 50, y: 50 })
    expect(f.project({ x: 0, y: 10 })).toEqual({ x: 0, y: 0 })
  })

  it('padding asymétrique', () => {
    const f = cartesianFrame({ width: 200, height: 100, padding: { left: 40, right: 10, top: 5, bottom: 15 } })
    expect(f.plot).toEqual({ x: 40, y: 5, width: 150, height: 80 })
  })
})

describe('radialPoints', () => {
  it('premier point en haut par défaut (-90°)', () => {
    const [p] = radialPoints({ cx: 50, cy: 50, radius: 40, count: 4 })
    expect(p.x).toBeCloseTo(50)
    expect(p.y).toBeCloseTo(10) // 50 - 40
  })

  it('répartit N points régulièrement', () => {
    const pts = radialPoints({ cx: 0, cy: 0, radius: 10, count: 4 })
    expect(pts).toHaveLength(4)
    // 4 points cardinaux : haut, droite, bas, gauche
    expect(pts[1].x).toBeCloseTo(10)
    expect(pts[1].y).toBeCloseTo(0)
    expect(pts[2].y).toBeCloseTo(10)
  })

  it('count ≤ 0 → aucun point', () => {
    expect(radialPoints({ cx: 0, cy: 0, radius: 10, count: 0 })).toEqual([])
  })

  it('radialPoint à 0° est à l’est', () => {
    const p = radialPoint(0, 0, 5, 0)
    expect(p.x).toBeCloseTo(5)
    expect(p.y).toBeCloseTo(0)
  })

  it('radialAngle répartit les axes', () => {
    expect(radialAngle(0, 4)).toBe(-90)
    expect(radialAngle(1, 4)).toBe(0)
  })
})

describe('quadrantGrid', () => {
  it('croix au centre par défaut', () => {
    const g = quadrantGrid({ width: 100, height: 100, padding: 0 })
    expect(g.center).toEqual({ x: 50, y: 50 })
  })

  it('découpe quatre cellules jointives couvrant l’aire', () => {
    const g = quadrantGrid({ width: 100, height: 100, padding: 0 })
    const { topLeft, topRight, bottomLeft, bottomRight } = g.cells
    expect(topLeft).toEqual({ x: 0, y: 0, width: 50, height: 50 })
    expect(topRight).toEqual({ x: 50, y: 0, width: 50, height: 50 })
    expect(bottomLeft).toEqual({ x: 0, y: 50, width: 50, height: 50 })
    expect(bottomRight).toEqual({ x: 50, y: 50, width: 50, height: 50 })
  })

  it('place un item selon ses deux scores (Y inversé)', () => {
    const g = quadrantGrid({ width: 100, height: 100, padding: 0, xDomain: [0, 10], yDomain: [0, 10] })
    // score haut sur les deux axes → quadrant haut-droite
    expect(g.place({ x: 10, y: 10 })).toEqual({ x: 100, y: 0 })
  })

  it('respecte un seuil de séparation explicite', () => {
    const g = quadrantGrid({ width: 100, height: 100, padding: 0, xDomain: [0, 10], xMid: 2 })
    expect(g.center.x).toBe(20)
  })
})

describe('lanes', () => {
  const area = { x: 0, y: 0, width: 100, height: 60 }

  it('colonnes verticales égales', () => {
    const { bands, band, centers } = lanes({ area, count: 4, orientation: 'vertical' })
    expect(bands).toHaveLength(4)
    expect(band).toBe(25)
    expect(bands[0]).toEqual({ x: 0, y: 0, width: 25, height: 60 })
    expect(centers[0]).toBe(12.5)
    expect(bands[3].x).toBe(75)
  })

  it('rangées horizontales égales', () => {
    const { bands, band } = lanes({ area, count: 3, orientation: 'horizontal' })
    expect(band).toBe(20)
    expect(bands[1]).toEqual({ x: 0, y: 20, width: 100, height: 20 })
  })

  it('retire les gaps de la largeur partagée', () => {
    const { band, bands } = lanes({ area, count: 2, orientation: 'vertical', gap: 10 })
    expect(band).toBe(45) // (100 - 10) / 2
    expect(bands[1].x).toBe(55) // 45 + 10
  })

  it('count ≤ 0 → aucune bande', () => {
    expect(lanes({ area, count: 0, orientation: 'vertical' }).bands).toEqual([])
  })
})

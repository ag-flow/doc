/** Grille de quadrants à deux axes.
 *  Base des diagrammes Quadrant et de la variante Consultant 2×2. */
import { linearScale, type Scale } from './scales'
import { resolvePadding, type Extent, type Padding, type Point, type Rect } from './types'

export interface QuadrantOptions {
  width: number
  height: number
  padding?: Padding
  /** Domaine de l'axe X. Défaut [0, 1]. */
  xDomain?: Extent
  /** Domaine de l'axe Y. Défaut [0, 1]. */
  yDomain?: Extent
  /** Valeur X de la séparation verticale. Défaut : milieu du domaine X. */
  xMid?: number
  /** Valeur Y de la séparation horizontale. Défaut : milieu du domaine Y. */
  yMid?: number
}

export interface QuadrantGrid {
  plot: Rect
  x: Scale
  y: Scale
  /** Point de croisement des deux axes, en pixels. */
  center: Point
  /** Les quatre cellules, coin haut-gauche + dimensions. */
  cells: { topLeft: Rect; topRight: Rect; bottomLeft: Rect; bottomRight: Rect }
  /** Place un item (x, y en données) dans l'aire, coordonnées écran. */
  place(pt: { x: number; y: number }): Point
}

/** Construit une grille à deux axes : aire, croix centrale, quatre cellules.
 *  L'axe Y est inversé (max en haut de l'écran). */
export function quadrantGrid(opts: QuadrantOptions): QuadrantGrid {
  const pad = resolvePadding(opts.padding ?? 0)
  const plot: Rect = {
    x: pad.left,
    y: pad.top,
    width: Math.max(0, opts.width - pad.left - pad.right),
    height: Math.max(0, opts.height - pad.top - pad.bottom),
  }
  const xDomain = opts.xDomain ?? [0, 1]
  const yDomain = opts.yDomain ?? [0, 1]
  const x = linearScale(xDomain, [plot.x, plot.x + plot.width])
  const y = linearScale(yDomain, [plot.y + plot.height, plot.y])
  const xMid = opts.xMid ?? (xDomain[0] + xDomain[1]) / 2
  const yMid = opts.yMid ?? (yDomain[0] + yDomain[1]) / 2
  const cx = x(xMid)
  const cy = y(yMid)
  const left = plot.x
  const right = plot.x + plot.width
  const top = plot.y
  const bottom = plot.y + plot.height
  const cells = {
    topLeft: { x: left, y: top, width: cx - left, height: cy - top },
    topRight: { x: cx, y: top, width: right - cx, height: cy - top },
    bottomLeft: { x: left, y: cy, width: cx - left, height: bottom - cy },
    bottomRight: { x: cx, y: cy, width: right - cx, height: bottom - cy },
  }
  return {
    plot,
    x,
    y,
    center: { x: cx, y: cy },
    cells,
    place: (pt) => ({ x: x(pt.x), y: y(pt.y) }),
  }
}

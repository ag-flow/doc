/** Repère cartésien : aire de tracé + échelles X/Y + projection de points.
 *  Base des diagrammes à axes (Bar, Line, Scatter, Gantt). */
import { linearScale, timeScale, type Scale } from './scales'
import { resolvePadding, type Extent, type Padding, type Point, type Rect } from './types'

export interface CartesianOptions {
  /** Dimensions totales du canvas (viewBox), marges comprises. */
  width: number
  height: number
  /** Marge réservée aux axes/labels autour de l'aire de tracé. */
  padding?: Padding
  /** Domaine X (données). Défaut [0, 1]. */
  xDomain?: Extent
  /** Domaine Y (données). Défaut [0, 1]. */
  yDomain?: Extent
  /** Échelle temporelle sur X (domaine en epoch-ms). Défaut : linéaire. */
  xScale?: 'linear' | 'time'
}

export interface CartesianFrame {
  /** Aire de tracé (intérieur des marges). */
  plot: Rect
  /** Échelle X : domaine → pixels (gauche → droite). */
  x: Scale
  /** Échelle Y : domaine → pixels, INVERSÉE (bas de l'aire = min). */
  y: Scale
  /** Projette un point de données en coordonnées écran. */
  project(pt: { x: number; y: number }): Point
  xTicks: number[]
  yTicks: number[]
}

/** Construit un repère cartésien prêt à tracer.
 *  L'axe Y est inversé (l'écran croît vers le bas, la donnée vers le haut). */
export function cartesianFrame(opts: CartesianOptions): CartesianFrame {
  const pad = resolvePadding(opts.padding ?? 0)
  const plot: Rect = {
    x: pad.left,
    y: pad.top,
    width: Math.max(0, opts.width - pad.left - pad.right),
    height: Math.max(0, opts.height - pad.top - pad.bottom),
  }
  const xDomain = opts.xDomain ?? [0, 1]
  const yDomain = opts.yDomain ?? [0, 1]
  const x =
    opts.xScale === 'time'
      ? timeScale([xDomain[0], xDomain[1]], [plot.x, plot.x + plot.width])
      : linearScale(xDomain, [plot.x, plot.x + plot.width])
  // Plage inversée : yDomain min → bas de l'aire, max → haut.
  const y = linearScale(yDomain, [plot.y + plot.height, plot.y])
  return {
    plot,
    x,
    y,
    project: (pt) => ({ x: x(pt.x), y: y(pt.y) }),
    xTicks: x.ticks(),
    yTicks: y.ticks(),
  }
}

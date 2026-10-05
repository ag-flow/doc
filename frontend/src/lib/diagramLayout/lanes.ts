/** Bandes (lanes) horizontales ou verticales de largeur égale.
 *  Base des diagrammes Sequence (colonnes d'acteurs) et Swimlane (rangées). */
import type { Rect } from './types'

export interface LanesOptions {
  /** Aire à découper. */
  area: Rect
  /** Nombre de bandes. */
  count: number
  /** 'vertical' = colonnes côte à côte ; 'horizontal' = rangées empilées. */
  orientation: 'horizontal' | 'vertical'
  /** Espace entre bandes (pixels). Défaut 0. */
  gap?: number
}

export interface Lanes {
  /** Rectangle de chaque bande, dans l'ordre. */
  bands: Rect[]
  /** Axe central de chaque bande (x pour vertical, y pour horizontal). */
  centers: number[]
  /** Épaisseur d'une bande (largeur si vertical, hauteur si horizontal). */
  band: number
}

/** Découpe `area` en `count` bandes égales séparées par `gap`.
 *  vertical → colonnes (réparties sur la largeur) ; horizontal → rangées. */
export function lanes(opts: LanesOptions): Lanes {
  const { area, count, orientation } = opts
  const gap = opts.gap ?? 0
  if (count <= 0) return { bands: [], centers: [], band: 0 }
  const vertical = orientation === 'vertical'
  const total = vertical ? area.width : area.height
  // La largeur cumulée des gaps est retirée avant de partager le reste.
  const band = Math.max(0, (total - gap * (count - 1)) / count)
  const bands: Rect[] = []
  const centers: number[] = []
  for (let i = 0; i < count; i++) {
    const offset = i * (band + gap)
    if (vertical) {
      const x = area.x + offset
      bands.push({ x, y: area.y, width: band, height: area.height })
      centers.push(x + band / 2)
    } else {
      const y = area.y + offset
      bands.push({ x: area.x, y, width: area.width, height: band })
      centers.push(y + band / 2)
    }
  }
  return { bands, centers, band }
}

/** Placement circulaire / polygonal.
 *  Base des diagrammes radiaux (Radar) et des cercles (Venn). */
import type { Point } from './types'

export interface RadialOptions {
  /** Centre du cercle. */
  cx: number
  cy: number
  /** Rayon de placement. */
  radius: number
  /** Nombre de points régulièrement répartis. */
  count: number
  /** Angle du premier point, en degrés. Défaut -90 (haut, 12 h). */
  startAngleDeg?: number
  /** Sens horaire (défaut) ou trigonométrique. */
  clockwise?: boolean
}

/** Un point sur un cercle à un angle donné (degrés, 0 = est, sens écran). */
export function radialPoint(cx: number, cy: number, radius: number, angleDeg: number): Point {
  const a = (angleDeg * Math.PI) / 180
  return { x: cx + radius * Math.cos(a), y: cy + radius * Math.sin(a) }
}

/** `count` points régulièrement répartis sur le cercle — sommets d'un polygone
 *  régulier (axes d'un radar, secteurs). Le premier est à `startAngleDeg`. */
export function radialPoints(opts: RadialOptions): Point[] {
  const { cx, cy, radius, count } = opts
  if (count <= 0) return []
  const start = opts.startAngleDeg ?? -90
  const dir = opts.clockwise === false ? -1 : 1
  const step = 360 / count
  return Array.from({ length: count }, (_, i) => radialPoint(cx, cy, radius, start + dir * i * step))
}

/** Angle (degrés) du i-ᵉ axe d'un radar à `count` axes. */
export function radialAngle(index: number, count: number, startAngleDeg = -90, clockwise = true): number {
  const dir = clockwise ? 1 : -1
  return startAngleDeg + dir * (360 / Math.max(1, count)) * index
}

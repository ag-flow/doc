/** Échelles linéaires et temporelles (données → pixels). */
import type { Extent } from './types'

/** Échelle affine d'un domaine vers une plage, réversible et graduable. */
export interface Scale {
  /** Projette une valeur du domaine vers la plage. */
  (value: number): number
  /** Inverse : d'une position de la plage vers le domaine. */
  invert(px: number): number
  /** Graduations « rondes » couvrant le domaine (~count valeurs). */
  ticks(count?: number): number[]
  domain: Extent
  range: Extent
}

/** Arrondit un pas à une valeur « ronde » (1, 2, 5 × puissance de 10). */
function niceStep(rough: number): number {
  if (rough <= 0) return 1
  const pow = Math.pow(10, Math.floor(Math.log10(rough)))
  const frac = rough / pow
  const nice = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10
  return nice * pow
}

/** Graduations rondes couvrant [min, max] avec ~count intervalles.
 *  Renvoie des bornes alignées sur un pas rond, min/max inclus si alignés. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return []
  if (min === max) return [min]
  const lo = Math.min(min, max)
  const hi = Math.max(min, max)
  const step = niceStep((hi - lo) / Math.max(1, count))
  const start = Math.ceil(lo / step - 1e-9) * step
  const out: number[] = []
  // Le nombre de crans est borné : une plage dégénérée ne boucle pas à l'infini.
  for (let v = start, i = 0; v <= hi + 1e-9 && i <= count + 2; v += step, i++) {
    // Recolle les erreurs d'arrondi flottant sur le pas.
    out.push(Math.abs(v) < step * 1e-9 ? 0 : Number(v.toFixed(10)))
  }
  return out
}

/** Échelle linéaire domain → range. Domaine plat → projette au milieu de la
 *  plage (évite une division par zéro et centre une série constante). */
export function linearScale(domain: Extent, range: Extent): Scale {
  const [d0, d1] = domain
  const [r0, r1] = range
  const span = d1 - d0
  const project = (value: number): number =>
    span === 0 ? (r0 + r1) / 2 : r0 + ((value - d0) / span) * (r1 - r0)
  const scale = project as Scale
  scale.invert = (px: number): number => {
    const rspan = r1 - r0
    return rspan === 0 ? d0 : d0 + ((px - r0) / rspan) * span
  }
  scale.ticks = (count = 5): number[] => niceTicks(d0, d1, count)
  scale.domain = domain
  scale.range = range
  return scale
}

/** Étendue [min, max] d'une série numérique (NaN ignorés). */
export function extentOf(values: number[]): Extent {
  let min = Infinity
  let max = -Infinity
  for (const v of values) {
    if (!Number.isFinite(v)) continue
    if (v < min) min = v
    if (v > max) max = v
  }
  return min === Infinity ? [0, 0] : [min, max]
}

/** Échelle temporelle : domaine exprimé en epoch-ms (Date acceptée), même
 *  interface que linearScale ; les graduations sont réparties uniformément. */
export function timeScale(domain: [Date | number, Date | number], range: Extent): Scale {
  const toMs = (d: Date | number): number => (d instanceof Date ? d.getTime() : d)
  return linearScale([toMs(domain[0]), toMs(domain[1])], range)
}

/** Étendue temporelle [minMs, maxMs] d'une série de dates. */
export function timeExtent(dates: Array<Date | number>): Extent {
  return extentOf(dates.map((d) => (d instanceof Date ? d.getTime() : d)))
}

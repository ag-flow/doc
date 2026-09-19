/**
 * Tracé orthogonal d'un lien (épic MLD — F6).
 *
 * **Fonction isolée**, comme exigé par le cadrage : `orthogonalRoute` est pure,
 * ne connaît ni React, ni React Flow, ni elkjs. Elle prend deux ancres et rend
 * une suite de points. Tout le reste du canvas s'appuie dessus — c'est le seul
 * endroit où se décide la forme d'un lien, donc le seul à corriger si elle
 * déplaît.
 *
 * Les segments sont strictement horizontaux ou verticaux : c'est la convention
 * de lecture d'un modèle de données.
 */

import type { Anchor } from './anchor'
import type { Point, Side } from './model'

/** Longueur du segment qui décolle perpendiculairement au bord avant de tourner. */
export const STUB = 24

function stubPoint(from: Point, side: Side, length = STUB): Point {
  switch (side) {
    case 'left':
      return { x: from.x - length, y: from.y }
    case 'right':
      return { x: from.x + length, y: from.y }
    case 'top':
      return { x: from.x, y: from.y - length }
    case 'bottom':
      return { x: from.x, y: from.y + length }
  }
}

const horizontal = (side: Side) => side === 'left' || side === 'right'

/** Retire les points alignés consécutifs : un coude qui ne tourne pas n'existe pas. */
export function simplify(points: Point[]): Point[] {
  const out: Point[] = []
  for (const p of points) {
    const last = out[out.length - 1]
    if (last && last.x === p.x && last.y === p.y) continue // doublon
    out.push(p)
  }
  for (let i = 1; i < out.length - 1; ) {
    const a = out[i - 1]
    const b = out[i]
    const c = out[i + 1]
    const colinear = (a.x === b.x && b.x === c.x) || (a.y === b.y && b.y === c.y)
    if (colinear) out.splice(i, 1)
    else i++
  }
  return out
}

/** Relie deux points par des segments orthogonaux, en partant dans `axis`. */
function elbow(from: Point, to: Point, axis: 'h' | 'v'): Point[] {
  if (from.x === to.x || from.y === to.y) return [from, to] // déjà aligné
  const corner = axis === 'h' ? { x: to.x, y: from.y } : { x: from.x, y: to.y }
  return [from, corner, to]
}

/**
 * Tracé complet entre deux ancres.
 *
 * `waypoints` (coordonnées absolues) sont les coudes imposés par l'utilisateur :
 * quand ils existent, le tracé les traverse dans l'ordre au lieu d'être déduit.
 * Une intention explicite ne se fait jamais écraser par un recalcul.
 */
export function orthogonalRoute(
  source: Anchor,
  target: Anchor,
  waypoints?: Point[],
): Point[] {
  const start = source.point
  const end = target.point
  const startStub = stubPoint(start, source.side)
  const endStub = stubPoint(end, target.side)

  if (waypoints && waypoints.length > 0) {
    // Les coudes de l'utilisateur pilotent ; les moignons restent pour que le
    // lien quitte et rejoigne les boîtes perpendiculairement.
    const points: Point[] = [start, startStub]
    let cursor = startStub
    let axis: 'h' | 'v' = horizontal(source.side) ? 'v' : 'h'
    for (const w of waypoints) {
      points.push(...elbow(cursor, w, axis).slice(1))
      cursor = w
      axis = axis === 'h' ? 'v' : 'h'
    }
    points.push(...elbow(cursor, endStub, axis).slice(1), end)
    return simplify(points)
  }

  // Tracé automatique : on décolle des deux bords, puis on relie les deux
  // moignons. Deux coudes suffisent dans le cas nominal (droite → gauche).
  const sameAxis = horizontal(source.side) === horizontal(target.side)
  if (sameAxis) {
    const mid = horizontal(source.side)
      ? { x: (startStub.x + endStub.x) / 2, y: 0 }
      : { x: 0, y: (startStub.y + endStub.y) / 2 }
    const points = horizontal(source.side)
      ? [start, startStub, { x: mid.x, y: startStub.y }, { x: mid.x, y: endStub.y }, endStub, end]
      : [start, startStub, { x: startStub.x, y: mid.y }, { x: endStub.x, y: mid.y }, endStub, end]
    return simplify(points)
  }

  // Bords d'axes différents : un seul coude entre les deux moignons.
  const axis: 'h' | 'v' = horizontal(source.side) ? 'h' : 'v'
  return simplify([start, startStub, ...elbow(startStub, endStub, axis).slice(1), end])
}

/** Suite de points → attribut `d` d'un `<path>` SVG. */
export function toSvgPath(points: Point[]): string {
  if (points.length === 0) return ''
  const [first, ...rest] = points
  return `M ${first.x},${first.y}` + rest.map((p) => ` L ${p.x},${p.y}`).join('')
}

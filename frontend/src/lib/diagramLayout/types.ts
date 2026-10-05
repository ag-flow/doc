/** Socle de layout algorithmique (Lot 0) — types géométriques partagés.
 *
 *  Ce module ne fait QUE du calcul (données → géométrie) : aucune dépendance
 *  React, aucun rendu, aucun token de style. Les composants de diagramme
 *  (Lots 1-5) consomment ces coordonnées et posent le SVG eux-mêmes. */

/** Point dans le repère écran (y croît vers le bas). */
export interface Point {
  x: number
  y: number
}

/** Rectangle aligné sur les axes, coin haut-gauche + dimensions. */
export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/** Intervalle numérique [min, max] — domaine ou plage d'une échelle. */
export type Extent = [number, number]

/** Marge interne : un nombre (uniforme) ou par côté. */
export type Padding = number | { top?: number; right?: number; bottom?: number; left?: number }

/** Normalise un Padding en quadruplet explicite. */
export function resolvePadding(p: Padding): { top: number; right: number; bottom: number; left: number } {
  if (typeof p === 'number') return { top: p, right: p, bottom: p, left: p }
  return { top: p.top ?? 0, right: p.right ?? 0, bottom: p.bottom ?? 0, left: p.left ?? 0 }
}

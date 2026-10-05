/**
 * Enveloppe d'un document de canvas (épic MLD — F4d).
 *
 * Sert à rendre un diagramme **à son étendue réelle** — pour l'impression, où
 * une fenêtre de visualisation n'a pas de sens : ce qu'elle ne montre pas
 * n'existe pas sur le papier.
 *
 * Ce que l'enveloppe couvre, et ce qu'elle ne peut pas couvrir :
 *
 * - les **boîtes** des nœuds (position + taille) — dans le modèle ;
 * - les **coudes** des liens (`waypoints`) — dans le modèle, et un coude peut
 *   parfaitement sortir de l'enveloppe des nœuds ;
 * - les **étiquettes** de lien et les **marques de cardinalité** — PAS dans le
 *   modèle. Ce sont des textes mesurés par le navigateur.
 *
 * D'où `LABEL_MARGIN` : une marge forfaitaire qui évite de rogner un libellé qui
 * dépasse à droite du dernier nœud. Elle ne remplace pas une mesure ; elle
 * garantit seulement que le rendu n'est pas coupé. La découpe en pages, elle,
 * mesure le DOM rendu — où les textes sont présents.
 *
 * Fonction pure : ni React, ni DOM.
 */

import type { CanvasDoc, Point } from './model'
import { nodeSize } from './model'

/** Marge autour du contenu : les textes portés par les liens ne sont pas dans
 *  le modèle et débordent de l'enveloppe géométrique. */
export const LABEL_MARGIN = 48

export interface Bounds {
  x: number
  y: number
  width: number
  height: number
}

/** Enveloppe vide — un document sans nœud n'a pas d'étendue. */
const EMPTY: Bounds = { x: 0, y: 0, width: 0, height: 0 }

/**
 * Rectangle englobant tout le contenu, marge de textes comprise.
 *
 * `x`/`y` peuvent être NÉGATIFS : rien n'oblige un diagramme à commencer à
 * l'origine. L'appelant translate de `-x`/`-y` pour caler le contenu en haut à
 * gauche de sa zone.
 */
export function contentBounds(doc: CanvasDoc): Bounds {
  const points: Point[] = []

  for (const node of doc.nodes) {
    const { width, height } = nodeSize(node)
    points.push(node.position)
    points.push({ x: node.position.x + width, y: node.position.y + height })
  }
  for (const edge of doc.edges) {
    for (const w of edge.waypoints ?? []) points.push(w)
  }

  if (points.length === 0) return EMPTY

  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const minX = Math.min(...xs) - LABEL_MARGIN
  const minY = Math.min(...ys) - LABEL_MARGIN
  return {
    x: minX,
    y: minY,
    width: Math.max(...xs) + LABEL_MARGIN - minX,
    height: Math.max(...ys) + LABEL_MARGIN - minY,
  }
}

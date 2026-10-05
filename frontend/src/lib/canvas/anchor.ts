/**
 * Ancrage d'un lien sur un nœud (épic MLD — F6).
 *
 * Deux règles, toutes deux exigées par le cadrage :
 *
 * 1. **Ancrage sur le port** — un lien part à hauteur du port porteur et arrive
 *    à hauteur du port cible, pas au milieu de la boîte. C'est ce qui rend un
 *    modèle de données lisible quand une table a vingt champs.
 *
 * 2. **Dégradation vers le bord** — dès que le port n'est pas atteignable
 *    (nœud replié, palier de zoom qui masque les lignes, port supprimé depuis
 *    que le lien a été créé), l'ancre retombe sur le bord de la boîte. Un lien
 *    ne doit jamais disparaître ni pointer dans le vide parce que sa cible fine
 *    n'est plus affichée.
 *
 * Fonctions pures : aucune dépendance au moteur de rendu, testables seules.
 */

import type { CanvasNode, Point, Side } from './model'
import { nodeSize } from './model'

/** Ce que l'appelant sait de l'état d'affichage au moment du tracé. */
export interface AnchorContext {
  /** Les ports sont-ils visibles à ce palier de zoom ? */
  portsVisible: boolean
}

export interface Anchor {
  point: Point
  side: Side
  /** Vrai si l'ancrage a dû retomber sur le bord faute de port utilisable. */
  degraded: boolean
}

/**
 * Côté d'accroche d'après la position RELATIVE des deux nœuds.
 *
 * Cas nominal d'un modèle de données : la source sort à droite, la cible entre à
 * gauche. On inverse quand la cible est à gauche, pour que le lien n'ait pas à
 * contourner sa propre boîte. Le choix se fait sur l'axe dominant : deux nœuds
 * l'un au-dessus de l'autre s'accrochent en haut/bas.
 */
export function sidesFor(source: CanvasNode, target: CanvasNode): [Side, Side] {
  const s = nodeSize(source)
  const t = nodeSize(target)
  const sourceCenter = { x: source.position.x + s.width / 2, y: source.position.y + s.height / 2 }
  const targetCenter = { x: target.position.x + t.width / 2, y: target.position.y + t.height / 2 }

  const dx = targetCenter.x - sourceCenter.x
  const dy = targetCenter.y - sourceCenter.y

  // Axe dominant : on ne bascule en vertical que si l'écart vertical l'emporte
  // nettement, sinon un simple décalage ferait sauter le lien d'un côté à l'autre.
  if (Math.abs(dy) > Math.abs(dx)) {
    return dy >= 0 ? ['bottom', 'top'] : ['top', 'bottom']
  }
  return dx >= 0 ? ['right', 'left'] : ['left', 'right']
}

/** Point milieu d'un côté de la boîte — l'ancrage dégradé. */
function edgePoint(node: CanvasNode, side: Side): Point {
  const { width, height } = nodeSize(node)
  const { x, y } = node.position
  switch (side) {
    case 'left':
      return { x, y: y + height / 2 }
    case 'right':
      return { x: x + width, y: y + height / 2 }
    case 'top':
      return { x: x + width / 2, y }
    case 'bottom':
      return { x: x + width / 2, y: y + height }
  }
}

/**
 * Ancre d'un lien sur `node`, à hauteur de `portId` si c'est possible.
 *
 * Retombe sur le bord — sans jamais échouer — quand le port est absent, inconnu,
 * masqué par le palier de zoom, ou que le nœud est replié.
 */
export function anchorPoint(
  node: CanvasNode,
  portId: string | undefined,
  side: Side,
  ctx: AnchorContext = { portsVisible: true },
): Anchor {
  const fallback: Anchor = { point: edgePoint(node, side), side, degraded: true }

  if (!portId || node.collapsed || !ctx.portsVisible) return fallback
  // Un port ne borde que la gauche ou la droite : en haut/bas, la hauteur du
  // port n'a pas de sens, on garde le milieu du côté.
  if (side === 'top' || side === 'bottom') return fallback

  const port = node.ports?.find((p) => p.id === portId)
  if (!port) return fallback

  const { width, height } = nodeSize(node)
  // Borné à la boîte : un offset périmé (contenu réduit depuis) ne doit pas
  // faire sortir l'ancre du nœud.
  const y = node.position.y + Math.min(Math.max(port.offset, 0), height)
  return {
    point: { x: side === 'right' ? node.position.x + width : node.position.x, y },
    side,
    degraded: false,
  }
}

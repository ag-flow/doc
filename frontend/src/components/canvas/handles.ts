/**
 * Poignées d'ancrage du moteur de rendu (épic MLD — F6).
 *
 * Confiné à la frontière React Flow : une « poignée » n'existe que pour lui, et
 * n'apparaît ni dans le modèle persisté ni dans l'API publique du canvas.
 *
 * Une poignée porte un CÔTÉ, parce qu'un port borde les deux flancs de sa boîte.
 * C'est ce qui permet au lien de sortir du bon côté — sans quoi il contourne sa
 * propre boîte, passe dessous, et les marques d'extrémité se retrouvent posées
 * à l'opposé du trait qu'on voit.
 */

import type { Side } from '../../lib/canvas/model'

/** Ancrage de repli quand aucun port n'est utilisable (cf. `anchor.ts`). */
export const BOX_PORT = '__box'

/** Les quatre côtés — le repli sur la boîte peut s'accrocher partout. */
export const SIDES: Side[] = ['left', 'right', 'top', 'bottom']

/** Un port ne borde que la gauche et la droite : en haut/bas, sa hauteur n'a
 *  pas de sens et l'ancrage dégrade vers le bord (même règle qu'`anchorPoint`). */
export const PORT_SIDES: Side[] = ['left', 'right']

/** Identifiant de poignée : port + côté. */
export function handleId(portId: string, side: Side): string {
  return `${portId}::${side}`
}

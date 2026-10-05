/**
 * Contrat de pagination d'une surface de contenu (épic MLD — F4d).
 *
 * Deux régimes, parce qu'un **plan** n'est pas un **flux** :
 *
 * - `flow` — du contenu empilé verticalement (markdown, une grille de champs).
 *   Les coupures se calculent par `computeCuts`, qui sait ne pas trancher un
 *   composant ni laisser un titre orphelin.
 * - `plane` — une surface bidimensionnelle (un canevas). Elle ne se coupe pas,
 *   elle se **tuile** : on la découpe en pages et on les recolle.
 *
 * `FlowBlock` porte `top`/`bottom` : c'est une projection unidimensionnelle,
 * elle ne peut pas exprimer un tuilage. D'où deux régimes plutôt qu'un.
 *
 * Module neutre : ni React, ni DOM. Les surfaces le lisent sans dépendre de la
 * page d'impression.
 */

/** Un bloc de contenu en flux, projeté en 1D (positions en px depuis le haut).
 *  `component` = insécable (table, image, code…) ; `heading` = titre (jamais
 *  dernier sur une page) ; `break` = sécable (paragraphe, liste). */
export interface FlowBlock {
  top: number
  bottom: number
  kind: 'heading' | 'component' | 'break'
}

export type PrintLayout =
  | { mode: 'flow'; blocks: FlowBlock[] }
  | { mode: 'plane'; width: number; height: number }

/** Une tuile : sa place dans la grille, et l'origine du contenu qu'elle montre. */
export interface Tile {
  /** 1-based — c'est ce qui s'imprime sur la page pour la recoller. */
  col: number
  row: number
  /** Décalage du contenu à appliquer dans cette tuile (px, positifs). */
  x: number
  y: number
}

/** Au-delà, l'aperçu avertit. On n'interdit pas : interdire serait paternaliste,
 *  lancer quarante pages sans prévenir serait pire. */
export const TILE_WARN_THRESHOLD = 20

/**
 * Nombre de colonnes d'un plan — donc de COPIES du contenu que l'impression doit
 * émettre.
 *
 * Seul l'axe horizontal demande des copies : le navigateur sait couper
 * verticalement tout seul. Une copie par colonne, rognée et décalée, et la
 * coupure verticale naturelle produit exactement l'ordre voulu — toute la
 * colonne 1, puis toute la colonne 2.
 *
 * Rend 1 dans le cas de loin le plus fréquent (le contenu tient en largeur) :
 * aucune copie supplémentaire n'est alors émise.
 */
export function tileColumns(width: number, pageW: number): number {
  if (pageW <= 0 || width <= 0) return 0
  return Math.ceil(width / pageW)
}

/**
 * Découpe un plan en tuiles de la taille d'une page — la GRILLE d'aperçu.
 *
 * Règle arrêtée avec l'architecte : l'origine du contenu se cale sur le coin
 * **haut-gauche**, sans recadrage ni réduction ; on descend la première colonne
 * jusqu'en bas, puis on repart en haut de la suivante ; on s'arrête dès que le
 * point le plus en bas à droite est couvert.
 *
 * L'ordre est donc **par colonne**, pas par ligne. La dernière colonne et la
 * dernière ligne sont partiellement vides : c'est attendu, pas un défaut.
 *
 * Dégénérescence utile : un contenu qui n'est pas plus large qu'une page n'a
 * qu'une colonne — le tuilage se réduit alors de lui-même à un tranchage
 * vertical. C'est ce qui rend ce régime sûr comme repli universel.
 */
export function tileGrid(width: number, height: number, pageW: number, pageH: number): Tile[] {
  if (pageW <= 0 || pageH <= 0 || width <= 0 || height <= 0) return []
  const cols = Math.ceil(width / pageW)
  const rows = Math.ceil(height / pageH)

  const tiles: Tile[] = []
  for (let c = 0; c < cols; c++) {
    for (let r = 0; r < rows; r++) {
      tiles.push({ col: c + 1, row: r + 1, x: c * pageW, y: r * pageH })
    }
  }
  return tiles
}
